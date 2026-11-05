# Agent — packet RX2 implementation: the baseline

Status: **rev. 2, for independent re-review. Independent review of rev. 1 (`e66f48e`): NOT_READY (B1–B4; N1, N2), applied, §10.** Date: 2026-11-05. Design: [`agent-rx2-design.md`](agent-rx2-design.md)
(RX2-D) rev. 3 with amendments A1–A3 (§11), under [`agent-rx0-design.md`](agent-rx0-design.md). Base: `main @ d71496a`
(RX2-D merged, PR #142).

RX2 measured arms A (`commentary_ko_v8`) and A-min (`commentary_min_v1`) before anything is learned: 48 runs, a
blind judging in four parts, M1–M4 with their intervals, and the bounds for later arms. Nothing was promoted.

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `tools/rx/request.py` (new), `tools/rx/model.py` | each model request in a child process killed at its deadline (RX2-D §2) |
| `agent/record.py`, `agent/session.py` | a `build` line per engine start (`engine`, `profile`, `reasoning`, `build_id`); `shown` on every `call` line (the refs in the answer's text, `[]` on an error) |
| `tools/rx/run.py`, `tools/rx/__main__.py` | the build checked before the model is called and after the run; the task by game id (A1); an exception group logged by its errors (A1b) |
| `tools/rx/reference.py` (new) | `annotate` (the build into `base.json` after a cache-hit probe) and `reference` (24 references) |
| `tools/rx/requests.py` (new) | `on_request` causes run through Calliope: resolved position and moves, material per ply, the end search (A2) |
| `tools/rx/judge.py`, `tools/rx/prompts/judge_v1.md`, `judge_v1.schema.json` (new) | the bundle in parts outside the repository, the key apart, the audit, the join |
| `tools/rx/metrics.py`, `tools/rx/report.py` (new) | M1a–M4, decisive M2b, `on_request` matching, the hierarchical bootstrap, the report |
| `tools/rx/batch.py` (new) | the batch: both arms interleaved by game, three workers |
| `tools/rx/references_v1/` (new) | 24 references, key causes reviewed by the owner in two rounds |
| `tests/agent/test_record.py` | 26 tests in all (RX1's 20, RX2's 6 net) |

## 2. Departures and amendments

- **A1, the task by game id** (RX2-D §11). Batch `rx2-1` is void as a baseline: in 22 of 48 runs the agent
  retyped the PGN without its headers, opened another game, re-analysed it (50–145 plies a run) and could not
  match any reference. `rx2-2`, run with the id, is the baseline.
- **A1b.** `rx2-1`'s three arm A errors were logged only as a task group. Their cause is unknown. `rx2-2` had no
  error.
- **A2, key causes** (owner's review). Round 1's drafts were true but stopped at observations. Round 2: one
  decisive cause a moment, at most two supporting causes, each a chain to an outcome, each with a route
  (`in_digest` or `on_request`). The five `on_request` requests were run through Calliope and the causes
  rewritten from what they showed. The owner caught one cause that read as false (184800218248 ply 58:
  32.Rxa5+ "while the bishop guards a5"). Playing it out showed the bishop guards a5 right after 29...a5
  (30.Rxa5 Bxa5, −5.12) but has left by move 32 (+1.61). The cause now says so, and A2 requires a capture a
  cause names to be played out with its evaluation.
- **A3, the target.** `rapid` ply 40 (20...c6) has no key cause: Calliope shows no material or tactical reason
  (the line ends level, the material claims are inconclusive). The owner's reading (the bishop's diagonal and
  the central open files after 21.dxc6) is positional, level 3. It is left out of M2 and M3 and counted here.
- **The audit's rule, read narrowly.** RX2-D §5.1 voids a judging whose commands list or walk directories. The
  audit of the four transcripts (exported, every recorded tool call) found no path outside the part's
  directory and no read of the key or the records. It flagged six commands: part01's two are Python's
  `str.find`, not the shell's `find`; part03's four run `os.listdir('references')`, the part's own
  subdirectory. Read by its purpose (nothing read outside the directory), the audit passed, and the judging
  stands. The rule should say "outside the directory" (§9 Q2).
- **Where it ran.** WSL, as RX1 (`agent-rx1-implementation.md` §2). The build of both bases: `8124217c…`
  (Stockfish 19 Windows build, profile `d12_mpv5_v1`).

## 3. Tests

`tests/agent/test_record.py`: 26 passed. The whole suite in WSL: **1877 passed, 27 skipped**, the same 3 failed
and 2 errors as `main` (RX1 §3: the digest golden on the Windows engine build, four `zstd` tests). The RX2
additions after that run (the task by id, the error leaves, the requests, decisive M2b) passed with
`test_record.py`.

## 4. The runs

| Batch | Runs | Done | Whole | Fixed moments commented | Plies re-analysed | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `rx2-1` (void: A1) | 48 | 45 (3 errors, arm A) | 48 | 135 / 144 | 22 runs, 50–145 each | $0.82 |
| `rx2-2` (the baseline) | 48 | 48 | 48 | 144 / 144 | 0 | $0.78 |

`rx2-2` per arm and set (turns, tool calls: min / median / max):

| | A, Train | A, Validation | A-min, Train | A-min, Validation |
| --- | --- | --- | --- | --- |
| Turns | 10 / 12 / 17 | 9 / 13 / 20 | 8 / 12 / 20 | 10 / 14 / 19 |
| Tool calls | 18 / 22 / 32 | 19 / 27 / 37 | 16 / 23 / 33 | 20 / 29 / 38 |
| Seconds (median) | 186 | 216 | 164 | 216 |
| Cost | $0.187 | $0.207 | $0.179 | $0.209 |

No run in `rx2-2` called `open_game`: every one used the id the task gave.

## 5. The judging

Bundle `80ad6cfd`: 144 commentaries, four parts of six moments and 36 commentaries (both arms' three runs a
moment), Train and Validation apart. Four fresh sessions, one in each part's directory, the same `judge_v1`.
All four outputs validate. Audit: §2.

## 6. The baseline (`rx2-2`, judging `80ad6cfd`)

Means, with the 90% interval of each arm alone (bootstrap over games, runs, moments):

| Metric | A, Train | A, Validation | A-min, Train | A-min, Validation |
| --- | --- | --- | --- | --- |
| M1a refused subjects a run | 5.75 | 5.83 | 5.75 | 5.42 |
| M1b wrong per 100 sentences | 1.0 [0, 3.0] | 0.5 [0, 2.2] | 2.2 [0, 4.9] | 1.1 [0, 3.3] |
| M1c kinds | piece/side 1, old attack 1 | piece/side 1 | other 3, piece/side 1 | piece/side 1, other 1 |
| **M2b decisive cause explained** | **55%** [27, 85] | **50%** [22, 81] | 42% [17, 73] | 56% [25, 86] |
| M2b supporting explained | 8% | 23% | 50% | 37% |
| M2a decisive cause's items cited | 100% | 83% | 100% | 83% |
| M3 decisive, `on_request`: fetched | **0 / 3** | **0 / 6** | **0 / 3** | **0 / 6** |
| M4 score (1–5) | 3.86 [3.39, 4.31] | 3.69 [3.31, 4.08] | 3.53 [3.11, 3.94] | 3.94 [3.58, 4.33] |
| Sentences judged | 196 | 182 | 183 | 180 |

**Paired, A − A-min, by moment** (each moment's mean over its three runs; 90% interval over games, then moments):

| | Train | Validation |
| --- | --- | --- |
| M1b wrong per 100 (a ratio of sums) | −1.18 [−3.33, +0.92] | −0.52 [−2.19, +1.11] |
| M2b decisive explained | **+12 pts [+3, +21]** | −6 pts [−14, 0] |
| M4 score | **+0.33 [+0.19, +0.50]** | **−0.25 [−0.47, −0.03]** |

**The smallest difference this size can confirm.** Arm against arm, each alone, the intervals are ±30 points for
M2b: nothing at RX0-D §7.1's 10 points can be confirmed that way. Paired by moment they are ±7–9 points for M2b,
±0.15–0.22 for M4 and ±1.7–2.1 per 100 for M1b. Paired comparisons at four games and three runs can therefore
confirm RX0-D §7.1's sizes for M2b (10 points) and M4, and just reach M1b's (2 per 100), **at these games**. The
independent unit is still the game, and there are four (review N2): an interval over four games depends on
which four they are, and a difference confirmed here is confirmed for these games, not for chess commentary at
large. RX3–RX4 compare arms paired by moment on these Validation games; before a promoted lesson set is taken
as general, it is measured on Test, and adding Validation games (RX framing §8.1's reserve and games played
since) is the way to firm up a result that sits near its threshold.

## 7. What the baseline shows

1. **Half the decisive causes are explained.** Arm A carries the decisive cause to its outcome in about half
   its commentaries (55% Train, 50% Validation); supporting causes far less. Facts are rarely wrong (0.5–2 per
   100 sentences).
2. **Evidence the agent must fetch is never fetched.** The three moments whose decisive cause needs a call
   (Validation 185264271324 ply 45: the exchange compared with 23.dxe5; Validation 185371835722 ply 30: the
   game's real 16.Rxf2 continuation; Train fourth ply 56: the mate after 29.Qxd5) were never explored, in nine
   moment-runs of either arm: fetched 0 of 9. Every trial so far showed the same. This is RX4's first target
   (A3 level 2). (Rev. 1 counted Train's three as fetched: they cited the cause's digest items, which is not
   the request; review B1.)
3. **The guide v8 helps on Train and not on Validation.** Against A-min, v8 explains 12 more decisive causes in
   100 and scores 0.33 higher on Train, the games v1–v8 were tuned on; on Validation it is level on M2b and 0.25
   lower on M4. This is what RX framing §4.1 (review B4) feared: tuned on Train, the guide does not carry to new
   games. Two consequences: the known gap D-min must recover in RX4 exists on Train only; and a lesson promoted
   on Validation must beat B on Validation, not on Train.
4. **M2a overstates use.** Arm A cites a decisive cause's items in 83–100% of commentaries but explains it in
   about half. Citing a handle is not explaining the cause (RX framing B1). M2b, not M2a, is the measure.
5. **Refusals are steady.** About 5.5–5.8 refused subjects a run in both arms; they are corrected within the
   run (every moment ends commented).

## 8. The bounds (RX2-D §6)

From arm A's 24 runs, the 95th percentile plus 50%, rounded up. No run was censored (none reached RX1's
starting bounds), so these are fixed:

| | Max seen | 95th percentile | Bound |
| --- | ---: | ---: | ---: |
| Turns | 20 | 18 | 27 |
| Tool calls | 37 | 32 | 48 |
| Tokens | 1,099,634 | 825,546 | 1,238,319 |
| Seconds | 362 | 350 | 525 |

Arms that add work (B's retries, C's critic rounds, D's lessons asking for `explore`) will use more. Fixed at
A's need, they would be censored for doing what they are for (§9 Q3).

## 9. Owner questions

- **Q1 — Accept the baseline?** **Answered as recommended (2026-11-05).** `rx2-2` with judging `80ad6cfd`. Recommended: yes.
- **Q2 — The audit's rule.** **Answered as recommended (2026-11-05).** Void a judging for commands that list or walk **outside** its directory, not
  inside it (§2). Recommended: yes, an RX0-D amendment.
- **Q3 — Bounds for the arms that add work.** **Answered as recommended (2026-11-05).** Fix §8's bounds for A and B, and give C and D their own,
  measured on their first batch the same way (95th percentile plus 50%), with censoring reported.
  Recommended: yes. One bound for all would censor C and D for exploring.

## 10. Review dispositions — rev. 1 (`e66f48e`), independent review: NOT_READY

| Item | Finding | Disposition |
| --- | --- | --- |
| B1 | An `on_request` cause counted as fetched when the commentary cited its digest items, with no `explore` | Confirmed (Train fourth-56: items `c106`, `c115`, `b55`). Applied: `record_moments` gives `request_fetched` (a successful call served a handle matching the request) apart from `covered`; Available and Used of an `on_request` cause need the fetch. Train's 3/3 becomes **0/3**. Test: cited items without `explore` give `request_fetched` false |
| B2 | `shown` was read from the whole result, but the model gets only its text content (`show_game` keeps its document in `structured_content` alone) | Confirmed in `agent/server.py`. Applied: `shown` from the result's text blocks. Tests: a ref only in structured content is not shown; on the real `show_game` every shown ref is in the text |
| B3 | The audit's six flags failed it while the report went on; the join checked neither the schema nor completeness | Applied: the audit reads the exported transcript and passes listings inside the directory (RX2 Q2); `record_audit` keeps the result beside the key; `checked_judgings` refuses a part without a passed audit, invalid against the schema, with an item missing, twice or foreign, a sentence or a key cause not judged once; `report.py` reads only through it. The four parts pass (`rx-evidence/rx2/audit.txt`). Rev. 1's audit read `\n` in scripts as a path; the rule reads commands raw. Test: each refusal |
| B4 | M1b's interval averaged per-commentary rates while M1b is a ratio of sums; the paired results were not in versioned code | Applied: the bootstrap resamples (wrong, sentences) and takes the ratio, so its point is M1b; `report.py` computes the paired comparisons (`--pair A A-min`) into `report.json`. Numbers in §6 replaced |
| N1 | A moment-run with no commentary would drop out of M2b | Applied: moment-runs come from the batch records and fixed moments; one without a judged commentary counts as its decisive cause not explained. `rx2-2` has none |
| N2 | Four games are four units; "no more games needed" overstates | Applied: §6 says the sizes hold for these games, Test and more Validation games for generality |
