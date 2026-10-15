// The viewer as an MCP App (AG3-D §4, §5 App) under node: the bridge against a fake host window,
// with `show_game` documents written by test_viewer_app.py (before and after a new commentary).
"use strict";
const fs = require("fs");
const vm = require("vm");

const [html, casesPath] = process.argv.slice(2);
const source = fs.readFileSync(html, "utf8");
const script = source.slice(source.indexOf("<script>") + 8, source.lastIndexOf("</script>"));
const context = { console };
vm.createContext(context);
vm.runInContext(script, context);
const V = context.CalliopeViewer;
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const tick = () => new Promise((resolve) => setImmediate(resolve));
const plain = (x) => JSON.parse(JSON.stringify(x === undefined ? null : x));

/** A fake host: the parent window, the View's posts, its callbacks, timers and an observer. */
function host(size = { width: 400, height: 900 }) {
  const parent = { name: "host" };
  const h = { parent, posts: [], events: [], timers: new Map(), nextTimer: 1, observed: null,
              disconnected: false, size, ply: null };
  h.bridge = V.appBridge({
    parent,
    post: (m) => h.posts.push(plain(m)),
    onContext: (c) => h.events.push(["context", plain(c)]),
    onDocument: (doc, refreshed) => {
      h.ply = V.keptPly(doc, refreshed ? h.ply : undefined);  // the page's rule (load)
      h.events.push(["document", doc.plies.map((p) => p.ply), refreshed,
                     (doc.plies.find((p) => p.ai_commentary) || {}).ply || null, doc]);
    },
    onText: (t) => h.events.push(["text", t]),
    onError: (t) => h.events.push(["error", t]),
    onState: () => h.events.push(["state", h.bridge.canRefresh()]),
    observe: (cb) => { h.observed = cb; return () => { h.disconnected = true; }; },
    measure: () => ({ ...h.size }),
    setTimer: (fn, ms) => { const t = h.nextTimer++; h.timers.set(t, [fn, ms]); return t; },
    clearTimer: (t) => h.timers.delete(t),
  });
  h.from = (data) => h.bridge.receive({ source: parent, data });
  h.flush = () => { const due = [...h.timers.values()]; h.timers.clear(); due.forEach(([fn]) => fn()); };
  h.reply = (id, result) => h.from({ jsonrpc: "2.0", id, result });
  h.notify = (method, params) => h.from({ jsonrpc: "2.0", method, params });
  h.methods = () => h.posts.map((m) => m.method || (m.error ? `error ${m.error.code}` : "result"));
  return h;
}

const strip = (events) => events.map((e) => (e[0] === "document" ? e.slice(0, 4) : e));

(async () => {
  const out = {};

  // the handshake, the host's context, size notifications
  {
    const h = host();
    const started = h.bridge.start();
    out.initialize = h.posts[0];
    out.beforeReply = h.methods();
    h.reply(h.posts[0].id, { protocolVersion: "2026-01-26", hostInfo: { name: "fake" },
                             hostContext: { theme: "dark", containerDimensions: { width: 400, maxHeight: 600 } } });
    await started;
    out.afterReply = h.methods();
    out.contexts = h.events.filter((e) => e[0] === "context").map((e) => e[1]);
    out.debounce = [...h.timers.values()].map(([, ms]) => ms);
    h.flush();
    out.firstSize = h.posts[h.posts.length - 1];
    h.observed(); h.flush();  // the same size: nothing sent
    h.size = { width: 400, height: 1200 }; h.observed(); h.observed(); h.flush();  // debounced: one
    out.sizes = h.posts.filter((m) => m.method === "ui/notifications/size-changed").map((m) => m.params);
    h.notify("ui/notifications/host-context-changed", { theme: "light" });
    out.changed = h.events[h.events.length - 1];
    // another window's message, a foreign message, an unknown notification: ignored
    const posts = h.posts.length, events = h.events.length;
    h.bridge.receive({ source: { name: "other" }, data: { jsonrpc: "2.0", method: "ui/notifications/tool-result",
                                                          params: { structuredContent: cases.before } } });
    h.from({ method: "ui/notifications/tool-result", params: { structuredContent: cases.before } });
    h.notify("ui/notifications/unknown", {});
    h.notify("ui/notifications/tool-input-partial", { arguments: { game: "g1" } });
    out.ignored = [h.posts.length - posts, h.events.length - events, h.bridge.canRefresh()];
    // requests of the host: ping, an unknown one
    h.from({ jsonrpc: "2.0", id: 41, method: "ping" });
    h.from({ jsonrpc: "2.0", id: "x7", method: "ui/unknown-request", params: {} });
    out.requests = h.posts.slice(-2);
  }

  // a fixed container: no size notifications
  {
    const h = host();
    const started = h.bridge.start();
    h.reply(1, { hostContext: { containerDimensions: { width: 400, height: 500 } } });
    await started;
    h.observed(); h.flush();
    out.fixed = h.methods();
  }

  // results: a Calliope document, another tool's text, a cancellation, the initialize error
  {
    const h = host();
    const started = h.bridge.start();
    h.reply(1, { hostContext: {} });
    await started;
    h.notify("ui/notifications/tool-result", { content: [{ type: "text", text: "게임 g1" }], structuredContent: cases.before });
    h.notify("ui/notifications/tool-result", { content: [{ type: "text", text: "다른 도구의 <b>답</b>" }],
                                               structuredContent: { format: "something_else" } });
    h.notify("ui/notifications/tool-cancelled", { reason: "user" });
    out.results = strip(h.events.filter((e) => e[0] !== "context"));
    const failing = host();
    const refused = failing.bridge.start().then(() => "resolved", (err) => err.message);
    failing.from({ jsonrpc: "2.0", id: 1, error: { code: -32000, message: "no apps here" } });
    out.initError = [await refused, failing.methods()];
  }

  // refresh: the kept arguments, the updated document on the same ply, errors, one at a time
  {
    const h = host();
    const started = h.bridge.start();
    h.reply(1, { hostContext: {} });
    await started;
    out.noArguments = [h.bridge.canRefresh(), await h.bridge.refresh(), h.methods().includes("tools/call")];
    const kept = (args) => { h.notify("ui/notifications/tool-input", { arguments: args }); return h.bridge.canRefresh(); };
    out.arguments = [kept({ game: "g1", extra: 1 }), kept({ game: "" }), kept({ game: "g1", plies: 5 }),
                     kept([]), kept(null), kept({ game: "g1", plies: "15-20" })];
    h.notify("ui/notifications/tool-result", { structuredContent: cases.before });
    h.events.length = 0;
    const first = h.bridge.refresh();
    const call = h.posts[h.posts.length - 1];
    out.call = call;
    out.whilePending = [h.bridge.canRefresh(), h.bridge.refreshing(), await h.bridge.refresh(),
                        h.posts.filter((m) => m.method === "tools/call").length];
    h.reply(call.id, { content: [{ type: "text", text: "게임 g1" }], structuredContent: cases.after });
    await first;
    out.refreshed = strip(h.events);
    const doc = h.events.find((e) => e[0] === "document")[4];
    out.kept = [V.keptPly(doc, cases.ply), V.keptPly(doc, 999), V.keptPly(doc, undefined), V.keptPly(doc, 0)];
    const index = V.commentaryIndex({ doc }, doc.game);
    const before = V.commentaryIndex({ doc: cases.before }, cases.before.game);
    out.onPly = [before.plies.has(cases.ply), (index.plies.get(cases.ply) || {}).main ? index.plies.get(cases.ply).main.id : null];
    h.events.length = 0;
    const second = h.bridge.refresh();
    h.reply(h.posts[h.posts.length - 1].id, { isError: true, content: [{ type: "text", text: "캐시된 수가 없습니다" }] });
    await second;
    const third = h.bridge.refresh();
    h.from({ jsonrpc: "2.0", id: h.posts[h.posts.length - 1].id, error: { code: -32603, message: "host failed" } });
    await third;
    out.errors = strip(h.events);
    out.afterErrors = h.bridge.canRefresh();
  }

  // review B1: the host also sends the View's own call result as `tool-result`, in either order
  for (const order of ["notificationFirst", "responseFirst"]) {
    const h = host();
    const started = h.bridge.start();
    h.reply(1, { hostContext: {} });
    await started;
    h.notify("ui/notifications/tool-input", { arguments: { game: "g1" } });
    h.notify("ui/notifications/tool-result", { structuredContent: cases.before });
    h.ply = 3;  // the reader moved to ply 3 (the document starts on ply 1)
    h.events.length = 0;
    const done = h.bridge.refresh();
    const call = h.posts[h.posts.length - 1];
    const result = { content: [{ type: "text", text: "게임 g1" }], structuredContent: cases.after };
    h.notify("ui/notifications/tool-input", { arguments: { game: "g1" } });  // the host's echo
    if (order === "notificationFirst") {
      h.notify("ui/notifications/tool-result", result);
      h.reply(call.id, result);
    } else {
      h.reply(call.id, result);
      await done;
      h.notify("ui/notifications/tool-result", result);
    }
    await done;
    h.notify("ui/notifications/tool-result", result);  // a late duplicate
    out[order] = [strip(h.events).filter((e) => e[0] === "document"), h.ply, h.bridge.canRefresh()];
  }
  {
    // a new call of the model while nothing is pending: another document starts on its first ply
    const h = host();
    const started = h.bridge.start();
    h.reply(1, { hostContext: {} });
    await started;
    h.notify("ui/notifications/tool-result", { structuredContent: cases.before });
    h.ply = 3;
    h.notify("ui/notifications/tool-result", { structuredContent: cases.after });
    out.modelCall = [strip(h.events).filter((e) => e[0] === "document"), h.ply];
  }

  // teardown during a pending refresh
  {
    const h = host();
    const started = h.bridge.start();
    h.reply(1, { hostContext: {} });
    await started;
    h.notify("ui/notifications/tool-input", { arguments: { game: "g1" } });
    h.observed();  // a size notification waiting on its timer
    const pending = h.bridge.refresh();
    const call = h.posts[h.posts.length - 1];
    h.events.length = 0;
    h.from({ jsonrpc: "2.0", id: 99, method: "ui/resource-teardown", params: { reason: "closed" } });
    out.teardownAnswer = h.posts[h.posts.length - 1];
    out.teardownState = [h.disconnected, h.timers.size, h.bridge.closed(), h.bridge.canRefresh()];
    const posts = h.posts.length;
    h.reply(call.id, { structuredContent: cases.after });  // the dropped reply
    h.notify("ui/notifications/tool-result", { structuredContent: cases.after });
    h.from({ jsonrpc: "2.0", id: 100, method: "ping" });
    h.observed(); h.flush();
    out.afterTeardown = [h.posts.length - posts, await h.bridge.refresh(), strip(h.events)];
    out.pendingSettled = await Promise.race([pending.then(() => "settled"), tick().then(() => "dropped")]);
  }

  out.toolText = V.toolText({ content: [{ type: "text", text: "a" }, { type: "image" }, { type: "text", text: "b" }] });
  out.version = [V.APP_PROTOCOL, V.VIEWER_VERSION];
  console.log(JSON.stringify(out));
})().catch((err) => { console.error(err); process.exit(1); });
