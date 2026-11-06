# Agent MH — Haiku 5.5 as the runner's default model, with Anthropic's prompt caching

Status: rev. 2; independent review READY_WITH_CORRECTIONS (F1–F3) applied (§8). The owner chose one packet for the trial and the change
(2026-11-06): the trial's results below are the case for the switch, and merging this packet is the
switch. Scope: `tools/rx` (the RX runner). The deployment's model is HIMARI's setting, outside this
repository, and is not changed here (§7 Q1).

## 0. Why

RX4a (`agent-rx4-implementation.md` §8) left luna's commentary where RX2 found it: on Validation the
decisive key cause explained about half the time, and no lesson set beat its base. The owner asked
what raises the commentary's quality in a short time, and named three levers to try on one or two
games: the model (luna, Haiku), the input (the reference's level: each moment's digest and full view
given up front) and the writing rule of the key causes (RX2-D A2: one decisive cause, a chain from
the move to an outcome, a capture played out before it is claimed). Then a Claude Code session on
Haiku, since the harness might matter. The pilot (§2) pointed to the model; a blind judging on all of
Validation (§4) measured it.

## 1. The change

| File | Change |
| --- | --- |
| `tools/rx/model.py` | `DEFAULT_MODEL = "anthropic/claude-haiku-5.5"`. For a model `anthropic/…`, `body()` sends a copy of the messages with the system message and the last message whose content is text as one text part with `cache_control: {"type": "ephemeral"}` (two of Anthropic's four marks: the fixed prefix and the growing history). The loop's own list is never changed. `OpenRouter(…, cache=False)` sends none; the marks are made here only (review F1). Other providers are sent as before (OpenAI caches by itself). `session_id` (when given) goes in the body: OpenRouter's sticky-routing key, so a run's requests stay on the provider that holds its cache (review F2). The reply's usage adds `cached_tokens` and `cache_write_tokens` from `prompt_tokens_details`. |
| `tools/rx/run.py`, `tools/rx/__main__.py` | `RunSpec.model` and `run --model` default to `DEFAULT_MODEL`. `--model openai/gpt-6-luna` still runs luna. `RunSpec.cache` (default on) and the run's id as `session_id` go to `OpenRouter`; the `start` line records both under `parameters`. |
| `tests/agent/test_rx_model.py` (new) | the default; the two marks on an Anthropic request and the untouched list; one text message, one mark; another provider's body unchanged; `cache=False` sends no marks; `session_id` sent when given; a run passes its id and switch; the cached tokens in the usage. |

Unchanged: the guide (`commentary_ko_v8`), the server, the tools, the arms, the bounds (§7 Q2), the
judging and the report.

## 2. The pilot (two Validation games, one run an arm, not blind)

Games 185264271324 (15.O-O, 23.Rxe5, 34.Bb2+) and 184800218248 (6...c5, 29.Ra4, 29...a5); arm A's
setup through a wrapper (`rx-evidence/mh/pilot/trial.py`) that appends the A2 rules
(`pilot/a2_rules.md`) to the system prompt (`--rules`) and each moment's digest and `ply(view="full")`
(the reference without its key causes) to the task (`--ref`). The Claude Code arm: one fresh session
on Haiku per game, in a folder of its own with a `.mcp.json` to the same server on a copy of the base
and a `task.md` with the same guide, rules, task and data (`pilot/make_cc.py`). Read against the key
causes by the author (`pilot/results.md`):

| Arm | Decisive cause explained (6 moments) | Cost a run | Note |
| --- | --- | --- | --- |
| luna, RX2's arm A (3 runs a game) | about 3 | $0.02 | 15.O-O told as the knight's problem; 29...a5 without the material |
| Haiku | 5 | $0.81–0.85 | one wrong claim at 23.Rxe5 ("흑 퀸 … 4점을 잃습니다") |
| Haiku + rules + reference | 5 | $0.77–1.12 | as Haiku; 12–20 tool calls against 29–30; garbled Korean ("걹다", "흔 비숍") |
| luna + rules + reference | 1 | $0.06 | both runs ended at the token bound (2M): 5 of 6 moments without commentary |
| Claude Code, Haiku + rules + reference | 5 | not on OpenRouter | 8–11 tool calls; the plainest causal writing; one session could not read `task.md`'s long JSON lines and fetched the moments with `ply` |

Read: the model moved the result; the rules and the reference did not, and the reference's 60 KB a
moment broke luna's token bound. 23.Rxe5 (two exchange lines to compare, an `on_request` cause) was
missed by every arm.

## 3. Caching

Haiku cost about 40 times luna in the pilot although OpenRouter lists both at $0.10 / $0.50 per
million tokens. Two causes: OpenRouter caches an Anthropic model only at the request's `cache_control`
marks, which the runner did not send (luna was cached by OpenAI: about $0.03 a million in effect); and
Haiku's price is five times above 100,000 prompt tokens a request. One run with the marks (the
wrapper's `--cache`, the same marks as §1), Haiku alone on 185264271324:

| | Without marks | With marks |
| --- | --- | --- |
| Cost | $0.848 | **$0.138** |
| Input tokens | 1.94M | 1.22M |
| Turns / tool calls | 20 / 33 | 15 / 25 |
| Fixed moments saved | 3 | 3 |

From the second request on, all of the earlier prompt was read from the cache (e.g. 117,442 of
122,001); each turn wrote only its new tool results (`rx-evidence/mh/cache-usage.json`). Most of what
is left is the turns above 100,000 tokens. The two runs took different paths (20 turns, 33 calls
against 15, 25), so not all of the difference is the cache's; the recorded cache reads are what
support the saving (review). All MH runs were made without `session_id` (review F2).

## 4. Validation: Haiku against luna, blind

**Runs.** Batch `trial-haiku-1`: arm A (guide v8), Haiku with the marks, the four Validation games,
three runs each, through the wrapper without rules or reference; 12 runs, **$1.709** ($0.041–0.256 a
run; 10–19 turns, 18–35 tool calls). 11 ended `done`; one (184800218248) ended at the token bound
after saving all three moments and is counted. The rows carry `candidate: "haiku"`, so the report
labels the arm `A:haiku`; the records were copied into the RX runs directory. luna: RX2's arm A on
Validation (`rx2-2`, 12 runs, $0.207), same guide, bounds and base build.

**Judging `8b95714f`.** The 24 runs' 72 final commentaries, two parts of six moments, `judge_v1`,
one fresh Claude session a part (the RX4 brief, unchanged). Audit: part 1 passed; part 2 flagged one
command (recorded twice, calls 8 and 28): a `cd` into the part, then `glob('references/*.json')`
inside it, where OUTWARD took the backslashes of `split('\\')` in a string for a UNC path. Nothing
outside the directory was read or listed. **The owner accepted it as a false positive (2026-11-06)**;
`audit-part02.json` keeps both flags apart from the decision: `automated_passed: false`,
`owner_override` (date, decision, reason), `effective_passed: true`, and `passed: true`, which
`checked_judgings` reads (review F3).

**Report** (`rx-evidence/mh/validation-report.json`; `python -m tools.rx.report --batch rx2-2 --batch
trial-haiku-1 --judging 8b95714f --parts … --pair A:haiku A`; intervals 90%, paired by moment):

| Metric | luna (A) | Haiku (A:haiku) | Haiku − luna |
| --- | --- | --- | --- |
| **M2b decisive explained** | 0.50 (0.22–0.81) | **0.75** (0.58–0.92) | **+0.25 (+0.03 … +0.50)** |
| M4 score | 3.36 | **4.19** | +0.83 (+0.44 … +1.19) |
| M1b wrong per 100 sentences | 2.7 | 1.8 | −0.7 (−4.4 … +2.7) |
| M1c wrong kinds | piece or side 3, other 2 | other 4 | |
| Moment-runs without commentary | 0 of 36 | 0 of 36 | |
| Sentences | 182 | 217 | |
| M1a refusals a run | 5.8 | 9.6 | |
| Decisive `on_request` causes fetched | 0 of 6 | 0 of 6 | |
| Cost (12 runs) | $0.207 | $1.709 | about 8× |

The decisive gain comes from four moments (15.O-O +1.0, 185371835722 ply 31 +1.0, ply 32 +0.67,
29.Ra4 +0.33), none lost; the score is up at 11 of 12 moments. Against RX4-D §5's bar for a lesson
set (+0.10 with the interval above zero, no regression), the model passes where `lessons_v1` did not.

## 5. What is not solved, and the risks

- **Fetched evidence.** Neither model fetched any of the six decisive `on_request` causes. 23.Rxe5
  stays unexplained. This is the next lever, measured against this batch.
- **Korean.** Haiku garbled syllables in the pilot's API runs, as LM found
  (`agent-lm-implementation.md`: "비숋독", "지되"). The blind judging did not count any as wrong; it
  is not measured as such.
- **Refusals.** 9.6 a run against 5.8: more turns and tokens, every moment still saved.
- **Cost.** About $0.14 a run with caching, 8× luna. A 48-run batch is about $7.
- **The token bound** counts cached tokens (one run reached it). Kept at 2M for comparability (§7 Q2).
- **Baselines.** RX0–RX4's numbers are luna's. A comparison across this change pairs runs of one model.
- **Judgings differ.** The same 12 luna runs scored M4 3.69 and M1b 0.5 per 100 in RX2's judging
  `80ad6cfd`, against 3.36 and 2.7 here; M2b was 0.50 in both. Levels move between judgings; only a
  comparison inside one judging (as §4) is read.
- **Earlier records.** AG7–LM saw Haiku between luna and Sonnet in concreteness
  (`agent-commentary-path.md` F6) with one run a game and no key causes; this is the first measure of
  explanation, and it agrees.

## 6. Tests

`tests/agent/test_rx_model.py` 8 passed; with `test_rx4.py` and `test_record.py`: 59 passed,
1 skipped (WSL). `ruff check tools/rx tests/agent/test_rx_model.py` clean (the pilot's scripts under
`docs/` are evidence, outside ruff's scope).

## 7. Questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | The deployment (HIMARI) still runs luna. Switch it too? | Not in this packet: after the harness corrections are measured on Haiku. |
| Q2 | Count only uncached input against the token bound? | No: keep 2M as RX2 fixed it, so Haiku's runs stay comparable with the batch above. |
| Q3 | The audit's backslash false positive | A follow-up: read `\\` as a UNC path only at a token's start. |
| Q4 | Next | Harness corrections (the `on_request` gap, Korean, refusals), each against `trial-haiku-1` as the base. |

## 8. Review (rev. 1 → rev. 2)

Independent review of `b19f72e`: READY_WITH_CORRECTIONS.

| # | Finding | Disposition |
| --- | --- | --- |
| F1 (P2) | `pilot/trial.py --cache` marks again on top of `body()`'s marks (three marks with it, two without), so the cached and uncached runs cannot be reproduced after the merge | Applied: the marks are made in `OpenRouter.body` only, switched by `cache` (`RunSpec.cache`); the wrapper passes `--cache` through and its docstring says what the run's version (`b19f72e`) did. |
| F2 (P2) | No `session_id`: OpenRouter may route a run's requests to another provider and lose the cache | Applied: the run's id is sent as `session_id` (OpenRouter's documented sticky-routing key, `docs/features/prompt-caching`). The MH runs were made without it. |
| F3 (P3) | `audit-part02.json` mixes the automated result and the owner's approval | Applied to this judging's file: `automated_passed`, `owner_override`, `effective_passed`, with `passed` kept as the effective result for `checked_judgings`. The audit tool's own fields are left to Q3's follow-up. |
| Note | The cache test's two runs took different paths | §3 says so. |
| Note | Four games: the gain's size is not shown to hold elsewhere | Agreed; the Test set is untouched. |
