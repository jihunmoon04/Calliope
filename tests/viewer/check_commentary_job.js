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

  console.log(JSON.stringify({ urls: calls.map((c) => `${c.method} ${c.url}`), texts }));
})().catch((err) => {
  console.error(err.stack || err);
  process.exit(1);
});
