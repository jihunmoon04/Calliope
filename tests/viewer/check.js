// Runs the viewer's pure part (viewer/index.html) under node against cases written by
// test_viewer.py: python-chess positions, and calliope_result_v1 documents.
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
const key = (fen) => V.placementKey(V.parsePlacement(fen));
const out = { moves: 0, plies: 0, frames: [], svgPieces: 0 };

for (const c of cases.moves) {  // applyUci against python-chess
  const got = V.placementKey(V.applyUci(V.parsePlacement(c.fen), c.uci));
  if (got !== key(c.after)) throw new Error(`applyUci ${c.fen} ${c.uci}: ${got}`);
  out.moves += 1;
}
for (const doc of cases.documents) {
  const positions = V.gamePositions(doc);
  for (const p of doc.plies) {
    if (V.placementKey(positions[p.ply - 1]) !== key(p.fen_before)) throw new Error(`ply ${p.ply} before`);
    if (V.placementKey(positions[p.ply]) !== key(p.fen_after)) throw new Error(`ply ${p.ply} after`);
    out.plies += 1;
    for (const s of p.segments) {
      const frames = V.segmentFrames(s.refs);
      for (const r of s.refs) {
        if (r.kind === "line" && V.refFrames(r).length !== r.moves.length) throw new Error("line frames");
      }
      out.frames.push({ ply: p.ply, text: s.text, frames: frames.map((f) => ({
        rings: f.rings, arrows: f.arrows, caption: f.caption, board: V.placementKey(f.board) })) });
    }
  }
  const svg = V.boardSvg(positions[positions.length - 1], { flipped: true, rings: ["e4"], arrows: [["e2", "e4"]] });
  out.svgPieces += (svg.match(/︎<\/text>/g) || []).length;
}
console.log(JSON.stringify(out));
