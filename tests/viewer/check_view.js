// The board's document (AG6-D §6.1, §6.3) under node: how the page reads a calliope_view_v1, the
// line it shows for a ply it has no record of, the job's line, and how often it follows a job.
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
const read = (d) => {
  const { doc, view } = V.viewDocument(d);
  return { schema: doc.schema, plies: doc.plies.map((p) => p.ply), moves: doc.game.moves.length,
           provenance: doc.provenance !== null, states: view ? [...view.states.values()].map((e) => e.state) : null,
           job: view ? view.job : null, kept: V.keptPly(doc, 3) };
};
const out = {
  empty: read(cases.empty),
  analysed: read(cases.analysed),
  result: read(cases.analysed.result),  // a calliope_result_v1 is its own result
  intervals: [V.pollInterval(null), V.pollInterval({ state: "running" }), V.pollInterval({ state: "queued" }),
              V.pollInterval({ state: "waiting", resume_after_seconds: 2 }),
              V.pollInterval({ state: "waiting", resume_after_seconds: 30 }),
              V.pollInterval({ state: "waiting", resume_after_seconds: 900 }), V.pollInterval({ state: "done" })],
  states: [null, { state: "none" }, { state: "pending" }, { state: "failed" }, { state: "analysed" },
           { state: "analysed", omitted: "record" }].map(V.stateText),
  jobs: [V.jobText({ state: "running", done: 3, total: 10, seconds_left: 20 }),
         V.jobText({ state: "waiting", done: 4, total: 10, resume_after_seconds: 600 }),
         V.jobText({ state: "done", done: 10, total: 10 })],
};
process.stdout.write(JSON.stringify(out));
