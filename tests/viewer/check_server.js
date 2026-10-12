// The viewer's analysis-server client (AS-D §7, AS2) under node, with a mocked fetch.
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

/** A fetch that answers from `routes` (url → [status, body] or a list consumed in turn). */
function mock(routes) {
  const calls = [];
  const fetchFn = (url, init = {}) => {
    calls.push({ url, method: init.method || "GET", init });
    let answer = routes[`${init.method || "GET"} ${url}`];
    if (Array.isArray(answer) && Array.isArray(answer[0])) answer = answer.shift();
    if (!answer) answer = [404, { error: "not found" }];
    const [status, body] = answer;
    return Promise.resolve({ ok: status >= 200 && status < 300, status,
                             text: () => Promise.resolve(JSON.stringify(body)) });
  };
  return { fetchFn, calls };
}

const ID = "a".repeat(64);
const out = {};

(async () => {
  // the trailing slash
  assert.strictEqual(V.normalizedPath("/proxy/8765"), "/proxy/8765/");
  assert.strictEqual(V.normalizedPath("/proxy/8765/"), null);
  assert.strictEqual(V.normalizedPath("/"), null);
  assert.strictEqual(V.normalizedPath("/proxy/8765/index.html"), null);

  // a post, then queued → running → done, then the result
  const queued = { id: ID, state: "queued", queue_position: 2, plies: { total: 10, done: 0, cached: 0 }, game: {} };
  const running = { id: ID, state: "running", plies: { total: 10, done: 4, cached: 2 },
                    current: { ply: 5, san: "Bb5" }, eta_seconds: 75, game: { white: "Alice", black: "Bob" } };
  const done = { ...running, state: "done", plies: { total: 10, done: 10, cached: 2 } };
  const m = mock({
    "POST api/games": [202, queued],
    [`GET api/games/${ID}`]: [[200, queued], [200, running], [200, done]],
    [`GET api/games/${ID}/result`]: [200, { schema: "calliope_result_v1" }],
    "GET api/games": [200, { games: [done] }],
  });
  const client = V.serverClient(m.fetchFn);
  const posted = await client.post("1. e4 *", "1-10");
  assert.strictEqual(posted.status, 202);
  assert.deepStrictEqual(JSON.parse(m.calls[0].init.body), { pgn: "1. e4 *", plies: "1-10" });
  assert.strictEqual(m.calls[0].init.headers["Content-Type"], "application/json");
  const noRange = V.serverClient(mock({ "POST api/games": [202, queued] }).fetchFn);
  await noRange.post("1. e4 *", "");
  const seen = [];
  let waits = 0;
  const last = await V.pollJob(client, ID, (s) => seen.push(s.state), () => { waits += 1; return Promise.resolve(); });
  assert.deepStrictEqual(seen, ["queued", "running", "done"]);
  assert.strictEqual(waits, 2);
  assert.strictEqual(last.state, "done");
  const result = await client.result(ID);
  assert.strictEqual(result.body.schema, "calliope_result_v1");
  assert.strictEqual((await client.list()).body.games.length, 1);

  // every URL the client asked for is relative (AS-D S7)
  for (const c of m.calls) assert.ok(!c.url.startsWith("/") && !/^[a-z]+:/i.test(c.url), c.url);
  out.urls = m.calls.map((c) => `${c.method} ${c.url}`);

  // failures: a failed job ends the poll; a 404 throws; a 400 body is readable
  const failed = { id: ID, state: "failed", error: "ply 1: refused", plies: { total: 2, done: 0 } };
  const f = V.serverClient(mock({ [`GET api/games/${ID}`]: [200, failed] }).fetchFn);
  assert.strictEqual((await V.pollJob(f, ID, () => {}, () => Promise.resolve())).state, "failed");
  const gone = V.serverClient(mock({}).fetchFn);
  await assert.rejects(V.pollJob(gone, ID, () => {}, () => Promise.resolve()), /not found/);
  const bad = V.serverClient(mock({ "POST api/games": [400, { error: "no game in the PGN" }] }).fetchFn);
  const refused = await bad.post("", "");
  assert.strictEqual(refused.ok, false);
  assert.strictEqual(refused.body.error, "no game in the PGN");

  // the status line
  out.texts = [queued, running, done, failed, { ...queued, queue_position: 1 }].map(V.progressText);
  out.title = V.gameTitle({ white: "Alice", black: "Bob", date: "2026.10.12" });
  out.durations = [5, 75, 120, 3600].map(V.durationText);
  console.log(JSON.stringify(out));
})().catch((err) => { console.error(err.stack || err); process.exit(1); });
