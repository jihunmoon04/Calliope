// The viewer's AI commentary part (AG3-D D1–D8, D12, D14) under node, against cases written by
// test_viewer_ai.py: a game, a commentary listing built by calliope.server, a combined document.
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
const out = {};

const placed = (index) => ({
  plies: Object.fromEntries([...index.plies].map(([ply, slot]) => [ply, {
    main: slot.main ? slot.main.id : null,
    others: slot.others.map((o) => [o.c.id, o.tag]),
  }])),
  offGame: index.offGame.map((o) => [o.c.id, o.tag]),
  any: index.any,
});

const index = V.commentaryIndex({ listing: cases.listing }, cases.game);
out.listing = placed(index);
out.doc = placed(V.commentaryIndex({ doc: cases.doc }, cases.doc.game));
out.empty = placed(V.commentaryIndex({ listing: { plies: {}, judged: [] } }, cases.game));

const all = [...Object.values(cases.listing.plies).flat(), ...cases.listing.judged];
out.lines = {};
out.frames = {};
for (const c of all) {
  for (const p of c.propositions) {
    out.lines[`${c.id}/${p.id}`] = V.propositionLine(p);
    out.frames[`${c.id}/${p.id}`] = V.propositionFrames(p).map((f) => ({
      board: V.placementKey(f.board), rings: f.rings, arrows: f.arrows, caption: f.caption }));
  }
}
out.html = Object.fromEntries(all.map((c, k) => [c.id, V.commentaryHtml(c, k)]));
out.htmlJudged = Object.fromEntries(index.offGame.map((o, k) => [o.c.id, V.commentaryHtml(o.c, k, o)]));
out.hostile = V.commentaryHtml(cases.hostile, 0, { tag: "<i>x</i>" });
out.readable = cases.unreadable.map((c) => V.readableCommentary(c));
out.noDisplay = cases.noDisplay.map((p) => [V.propositionLine(p), V.propositionFrames(p).length]);
out.note = V.AI_NOTE;

const answer = (status, body) => Promise.resolve({ ok: status >= 200 && status < 300, status, body });
(async () => {
  const urls = [];
  const client = V.serverClient((url) => {
    urls.push(url);
    return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(cases.listing)) });
  });
  const ok = await V.fetchCommentary(client, "a".repeat(64), cases.game);
  const conflict = await V.fetchCommentary({ commentary: () => answer(409, { error: "the job's game cannot be read" }) },
                                           "x", cases.game);
  const thrown = await V.fetchCommentary({ commentary: () => Promise.reject(new Error("offline")) }, "x", cases.game);
  out.fetch = { urls, ok: [placed(ok.index).plies, ok.error], conflict: [conflict.index, conflict.error],
                thrown: [thrown.index, thrown.error] };
  console.log(JSON.stringify(out));
})().catch((err) => { console.error(err); process.exit(1); });
