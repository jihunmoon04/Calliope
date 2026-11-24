// The viewer's AI commentary job client and status text (local web app) under node.
"use strict";
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const [html] = process.argv.slice(2);
const source = fs.readFileSync(html, "utf8");
const script = source.slice(source.indexOf("<script>") + 8, source.lastIndexOf("</script>"));
const context = { console };
vm.createContext(context);
vm.runInContext(script, context);
const V = context.CalliopeViewer;

const calls = [];
const fetchFn = (url, init = {}) => {
  calls.push({ url, method: init.method || "GET", init });
  return Promise.resolve({
    ok: true,
    status: 200,
    text: () => Promise.resolve(JSON.stringify({ state: "queued" })),
  });
};

const ID = "b".repeat(64);

(async () => {
  const client = V.serverClient(fetchFn);
  await client.commentaryJob(ID);
  await client.startCommentary(ID);
  await client.cancelCommentary(ID);

  for (const c of calls) {
    assert.ok(!c.url.startsWith("/") && !/^[a-z]+:/i.test(c.url), c.url);
  }
  assert.deepStrictEqual(
    calls.map((c) => `${c.method} ${c.url}`),
    [
      `GET api/games/${ID}/commentary/job`,
      `POST api/games/${ID}/commentary`,
      `POST api/games/${ID}/commentary/cancel`,
    ],
  );
  assert.strictEqual(calls[1].init.headers["Content-Type"], "application/json");
  assert.strictEqual(calls[1].init.body, "{}");

  const texts = [
    null,
    { state: "idle", available: false },
    { state: "queued", queue_position: 1 },
    { state: "queued", queue_position: 3 },
    { state: "running", phase: "starting", accepted: 0, cost: 0 },
    { state: "running", phase: "tier2", current_ply: 14, tier2: { done: 1, total: 3 }, accepted: 1, cost: 0.04 },
    { state: "running", phase: "tier1", current_ply: 22, tier1: { done: 2, total: 5 }, accepted: 3, cost: 0.09 },
    { state: "running", phase: "finishing", accepted: 5, cost: 0.12 },
    { state: "running", cancelling: true, accepted: 2, cost: 0.05 },
    { state: "done", accepted: 6, cost: 0.14, end_reason: "done" },
    { state: "done", accepted: 4, cost: 1.0, end_reason: "cost" },
    { state: "done", accepted: 0, cost: 0.0, end_reason: "no_plies" },
    { state: "cancelled", accepted: 2, cost: 0.06 },
    { state: "failed", error: "API error" },
  ].map(V.commentaryJobText);

  // Browser-mode check: pollCommentaryJob retries transient 5xx/network errors and renderAiControls
  // updates status/buttons without wiping #ai-body DOM state.
  const dom = await runBrowserPollCheck();

  console.log(JSON.stringify({ urls: calls.map((c) => `${c.method} ${c.url}`), texts, dom }));

async function runBrowserPollCheck() {
  const makeNode = (id) => ({
    id,
    _html: "",
    textContent: "",
    value: "",
    hidden: false,
    disabled: false,
    dataset: {},
    style: {},
    className: "",
    classList: { add() {}, remove() {}, toggle() {} },
    querySelector: () => null,
    querySelectorAll: () => [],
    scrollIntoView() {},
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); },
  });
  const nodes = new Map();
  const getNode = (id) => {
    if (!nodes.has(id)) nodes.set(id, makeNode(id));
    return nodes.get(id);
  };
  let bodyWrites = 0;
  const aiBodyEl = makeNode("ai-body");
  Object.defineProperty(aiBodyEl, "innerHTML", {
    get() { return this._html; },
    set(v) { bodyWrites += 1; this._html = String(v); },
  });
  const aiActionsEl = makeNode("ai-actions");
  const aiJobWrapEl = makeNode("ai-job-wrap");
  const aiEl = makeNode("ai");
  aiEl.querySelector = (sel) => {
    if (sel === "#ai-body") return aiEl._html.includes('id="ai-body"') ? aiBodyEl : null;
    if (sel === ".ai-actions") return aiActionsEl;
    return null;
  };
  nodes.set("ai", aiEl);
  nodes.set("ai-body", aiBodyEl);
  nodes.set("ai-job-wrap", aiJobWrapEl);

  const delays = [];
  const requested = [];
  let jobPollCalls = 0;
  let retryWrapHtml = "";
  let retryBodyWrites = 0;
  let sentinelDuringPoll = false;
  let clearedErrorWrapHtml = "";

  const emptyCounts = () => ({ grades: {}, labels: {}, inconclusive: 0 });
  const docObj = {
    schema: "calliope_result_v1",
    provenance: null,
    grading: null,
    game: {
      headers: { white: "Alice", black: "Bob" },
      start_fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
      moves: [],
    },
    plies: [],
    summary: { white: emptyCounts(), black: emptyCounts() },
  };

  let doneResolve;
  const donePromise = new Promise((resolve) => { doneResolve = resolve; });

  const jobReplies = [
    () => ({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify({ available: true, state: "running", phase: "tier2", current_ply: 4, tier2: { done: 0, total: 1 }, tier1: { done: 0, total: 0 }, accepted: 0, cost: 0.01 })) }),
    () => ({ ok: false, status: 500, text: () => Promise.resolve(JSON.stringify({ error: "temporary server error" })) }),
    () => Promise.reject(new Error("network drop")),
    () => {
      retryWrapHtml = aiJobWrapEl.innerHTML;
      retryBodyWrites = bodyWrites;
      sentinelDuringPoll = aiBodyEl._sentinel === "keep-open";
      return { ok: true, status: 200, text: () => Promise.resolve(JSON.stringify({ available: true, state: "running", phase: "tier1", current_ply: 8, tier2: { done: 1, total: 1 }, tier1: { done: 1, total: 2 }, accepted: 0, cost: 0.02 })) };
    },
    () => {
      if (!clearedErrorWrapHtml) clearedErrorWrapHtml = aiJobWrapEl.innerHTML;
      return { ok: true, status: 200, text: () => Promise.resolve(JSON.stringify({ available: true, state: "done", accepted: 1, cost: 0.04, end_reason: "done" })) };
    },
  ];

  const mockFetch = (url, init = {}) => {
    const method = init.method || "GET";
    requested.push(`${method} ${url}`);
    if (url === `api/games/${ID}`) {
      return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify({ id: ID, state: "done", game: { white: "Alice", black: "Bob" } })) });
    }
    if (url === `api/games/${ID}/result`) {
      return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(docObj)) });
    }
    if (url === `api/games/${ID}/commentary`) {
      return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify({ plies: {}, judged: [] })) });
    }
    if (url === `api/games/${ID}/commentary/job`) {
      const idx = Math.min(jobPollCalls++, jobReplies.length - 1);
      const reply = jobReplies[idx]();
      if (idx === 0) {
        global.setTimeout(() => { aiBodyEl._sentinel = "keep-open"; }, 0);
      }
      if (idx === jobReplies.length - 1) {
        global.setTimeout(() => doneResolve(), 20);
      }
      return reply instanceof Promise ? reply : Promise.resolve(reply);
    }
    return Promise.resolve({ ok: false, status: 404, text: () => Promise.resolve("{}") });
  };

  const browserCtx = {
    console,
    URL,
    URLSearchParams,
    fetch: mockFetch,
    setTimeout: (fn, ms) => { delays.push(ms); return global.setTimeout(fn, 0); },
    clearTimeout: (t) => global.clearTimeout(t),
    location: { protocol: "http:", pathname: "/", search: `?game=${ID}`, href: `http://127.0.0.1/?game=${ID}`, hash: "" },
    history: { replaceState() {} },
    document: {
      documentElement: { dataset: {}, style: {} },
      body: { classList: { add() {}, remove() {}, toggle() {} }, getBoundingClientRect: () => ({ width: 400, height: 400 }) },
      getElementById: getNode,
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener() {},
    },
  };
  browserCtx.document.getElementById = (id) => (id === "calliope-doc" || id === "calliope-app" ? null : getNode(id));
  vm.createContext(browserCtx);
  vm.runInContext(script, browserCtx);
  let pollTimeout;
  try {
    await Promise.race([
      donePromise,
      new Promise((_, reject) => {
        pollTimeout = global.setTimeout(
          () => reject(new Error(`timed out waiting for commentary poll; app=${getNode("app").innerHTML}`)),
          3000,
        );
      }),
    ]);
  } finally {
    global.clearTimeout(pollTimeout);
  }

  const sentinelAfterDone = aiBodyEl._sentinel === "keep-open";
  const bodyWritesAtDone = bodyWrites;

  // Clicking #ai-refresh refreshes both commentary and commentary/job.
  const match = aiActionsEl.innerHTML.match(/id="ai-refresh"/);
  assert.ok(match, "ai-refresh button rendered");
  const refreshNode = getNode("ai-refresh");
  const beforeRefresh = requested.length;
  assert.strictEqual(typeof refreshNode.onclick, "function");
  refreshNode.onclick();
  await new Promise((r) => global.setTimeout(r, 10));
  const refreshCalls = requested.slice(beforeRefresh);

  return {
    delays,
    retryWrapHtml,
    clearedErrorWrapHtml,
    retryBodyWrites,
    bodyWritesAtDone,
    sentinelDuringPoll,
    sentinelAfterDone,
    finalWrapHtml: aiJobWrapEl.innerHTML,
    refreshCalls,
  };
}
})().catch((err) => {
  console.error(err.stack || err);
  process.exit(1);
});
