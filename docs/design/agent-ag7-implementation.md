# Agent — packet AG7 implementation: commentary guidance v2

Status: **rev. 1 — for independent review**. Date: 2026-10-17. Design:
[`agent-ag7-design.md`](agent-ag7-design.md) rev. 3 (AG7-D, approved and merged by the owner,
PR #111). Base: `main @ 08b208f`.

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/prompts/commentary_ko_v2.md` (new) | AG7-D Appendix A, byte for byte |
| `agent/build.py` | `PROMPTS = ("commentary_ko_v2", "check_ko_v1")`; `commentary_ko_v1.md` kept, unserved (H1, owner Q1) |
| `agent/server.py` | the prompt `calliope_commentary` and the resource `calliope://guides/commentary_ko` render `commentary_ko_v2.md`; `GUIDE_URIS` keyed by the new name; URIs and names unchanged |
| `agent/definitions.py` | `prompt.commentary_ko_v2` replaces `prompt.commentary_ko_v1`; `token_rule.move`'s statement gives the new pattern and the side rule (§5); `GUIDANCE_VERSION = "agent_guidance_v4"` |
| `agent/propositions.py` | a refused `use` answers `expected` with the uses the claim takes, in `USES`' order (§4) |
| `agent/sentences.py` | the move token `(?:(\d+)(\.|\.\.\.) ?|(\.\.\.))?SAN`; the bare-pawn-push exception only with neither number nor dots; `_move_ok` checks the side on the dots with or without a number, the number when written (§5, re-review N2) |
| `docs/design/agent-mcp-design.md` | amendment AM11 (AG-D §19) |
| tests | §3 below |

Not changed (H7): C, the digests, the instructions, `check_ko_v1`, tools and arguments
(`agent_tools_v5`), propositions and uses, sentence classes, `commentary_check_v1`, the viewer, the
reasoning build and every cache key.

## 2. Choices and departures (for the reviewer)

- **The guidance pin.** AG5-D G8's digest covers the instructions, the tool descriptions and the
  `definitions` search over a fixed registry; none of them changed, so `agent_guidance_v4` pins the
  same digest as v3 (a comment in `test_guidance.py` says why). The version still moves, as H6
  decides, because the guide an agent reads changed; `agent_build()["prompts"]` carries the new
  file's digest.
- **Castling after three dots.** `...O-O` had no digit and no bare castling form, so it was no
  token at all (unchecked prose). With three dots now part of a move, it is checked as Black's
  castling like `4...O-O`. Not in AG7-D §5's list; it follows from the rule.
- **The fixed moments.** AG7-D §7 names 27.Bxf7+ (ply 53) among the rapid game's fixed moments; it
  is not one of the moments `game_overview` chooses there (12, 13, 24, 40, 41, 51, 52, 54), so an
  agent that covers every moment may leave it out. The check adds 27...Nxf7 (ply 54, a moment) and
  reads criterion 3 as "every moment the server chose is commented". Ply 53 is listed where a trial
  commented it.
- **A line tried and withdrawn.** Reading ply 53's absence as a skipped moment, I added a line to the
  guide ("comment every moment") and ran AG7 three times more on each game ("a8", §4.3). The cause
  was the fixed moment, not the agent; the line is withdrawn, and the guide is Appendix A as merged.

## 3. Tests

- `test_guidance.py`: the resource and the prompt render `commentary_ko_v2.md`; `agent_guidance_v4`
  pinned; `definitions` finds `prompt.commentary_ko_v2` and not `prompt.commentary_ko_v1`; the v1
  file is still there.
- `test_server.py`: `agent_build()["prompts"]` names `commentary_ko_v2`.
- `test_propositions.py::test_a_refused_use_lists_the_uses_the_claim_takes`: a comparison claim as
  `result` → `["line_fact", "comparison"]`; a function claim → `["line_fact"]`; a mechanism claim
  with an `explains` relation as `comparison` → `["line_fact", "mechanism"]`; inconclusive →
  `["uncertain"]`; refuted → `["not_the_case"]`; each listed use is then accepted; an unknown use
  still lists `USES`.
- `test_commentary.py::test_three_dots_without_a_number_write_a_move_of_blacks`: accepted `...d6`,
  `...Nf6`, `1...d6`, `d6` (a square), `1.e4`, `e4`, `...dxe4`, `2...dxe4`, `...O-O`, `4...O-O`;
  refused `...e4` (White's), `1...e4`, `1.d6`, `.d6`, `...Nc6` (not cited), `...d5`, `...dxe4+`,
  `...d6+`, `2.dxe4`, `...O-O-O`, `...O-O+`; in a sentence, `...d6` passes and an uncited `e5` does
  not. The existing S3 tests pass unchanged.

Runs (`/home/coder/Calliope/.venv`, Python 3.12, Stockfish 19): `tests/agent` 291 passed;
the whole suite with Stockfish 1594 passed, 1 failed —
`test_game_jobs.py::test_a_cancel_while_the_job_is_active_always_ends_cancelled` refused a job
("5 jobs are running or queued"); it passes alone (3 of 3 runs of `test_game_jobs.py`) and touches
nothing of this packet. `ruff check` and `ruff format --check` clean.

## 4. Acceptance trial (AG7-D §7)

HIMARI v3 (`main @ 3120ef9`), Calliope over stdio in HIMARI's server sandbox, one shared process, an
empty data directory per trial, `openai/gpt-6-luna`; "today" is `main @ cbbd7da` (the guide
`commentary_ko_v1`), "AG7" this branch. The Opera Game and the rapid game 813–801, three trials each,
the request "이 대국을 분석하고 중요한 장면들을 해설해서 저장해 줘." with the PGN.

### 4.1 The criteria

| # | Criterion | Today | AG7 | |
| --- | --- | --- | --- | --- |
| 1 | no sentence wrong on the board | 0 wrong | 0 wrong | pass |
| 2 | no unestablished fact, cause or forced result; no forcing word without §3's evidence | 0 | 0; three borderline sentences (below) | pass, for the reviewer |
| 3 | every moment the server chose is commented (§2) | all, 6 trials | all, 6 trials | pass |
| 4 | every fixed moment has a sentence neither a restated judgement nor general | 20...c6: only restated, 3 of 3 | every moment, 6 of 6 | pass |
| 5 | more backed reasons than today on the Opera Game; the rapid game reported | Opera 6 of 9 sentences; rapid 5 of 11 | Opera 9 of 21; rapid 9 of 26 | pass |
| 6 | refusals a trial no more than today's; no `facts` family failure | 1, 2, 1 / 2, 1, 1 | 1 in every trial; 11 `facts` calls, none failed | pass |

Borderline (criterion 2): three AG7 sentences on the rapid game use "강제" (force) of a mate that a
cited server claim (`mate_allowed_v1`, `mate_found_v1`) holds along the engine line, each scoped to
it — "이 라인에서는 백이 메이트를 강제한다", "수순에서는 백이 메이트를 강제할 수 있었다", "킹을 향한 강제 공격". §3
lets the engine's judgement be said as the engine's, and keeps "must / cannot be met / the only
move" for what the board shows; these are the engine line's mate, scoped to the line, so they are
marked, not failed.

Backed reasons by §7's classes (a board fact, a line's material, a comparison after the same
reply). Board facts alone (`attack`, `pin`, ... propositions) were cited by neither guide in this
trial set; AG7's extra reasons on the Opera Game are the `fork_v2` claim (13.Rxd7 attacks a7, e7
and d8: "d7로 뛰어든 백 룩은 a7의 폰, e7의 퀸, d8의 룩을 동시에 겨누는 포크를 만들었습니다"), in every trial,
which today's guide never wrote.

### 4.2 Reported

| | Today | AG7 |
| --- | --- | --- |
| Opera Game, characters (3 trials) | 547 (467, 687, 487) | 951 (788, 1,018, 1,047) |
| Rapid game, characters | 420 (427, 346, 486) | 1,063 (1,253, 895, 1,040) |
| Interpretation sentences, all plies | 0 in 6 trials | in 5 of 6 trials |
| Cost a trial, Opera / rapid | $0.006 / $0.008 | $0.011 / $0.010 |

### 4.3 The withdrawn line ("a8", for the record)

With "comment every moment" added: Opera 1,013 characters, rapid 1,099; refusals 1 a trial; 26
`facts` calls, none failed, one board fact cited; the same moments commented. No difference that
the withdrawn line would explain.

## Appendix B — the fixed moments' sentences by guide

Classes: restated (a judgement said again), line (an engine line narrated), backed reason, reading
(an interpretation reaching a piece, a square or a line), general. Marks: wrong, unsupported,
unestablished — none found; borderline as §4.1.

### Opera Game

**ply 18 (9...b5)**

| trial | # | class | sentence | mark |
| --- | --- | --- | --- | --- |
| today 1 | 0 | backed reason | 9...b5는 실수였고, 9...a6가 더 나은 대안이었다. 특정 분석 라인에서는 흑의 b4 비숍이 14.cxb4로 잡힌다. |  |
| today 2 | 0 | backed reason | 9...b5는 실수였습니다. 이 수 뒤 엔진이 제시한 특정 변형에서는 10.Nxb5 이후 흑이 14.cxb4로 비숍을 잃어, 해당 라인에서 최소 2점의 기물 손실이 발생합니다. 9...a6가 더 나은 대안이었습니다. |  |
| today 3 | 0 | backed reason | 9...b5는 실수였다. 엔진 분석의 한 구체적인 라인에서는 백의 나이트가 잡힌 뒤 14.cxb4로 흑의 비숍까지 잃는 물질 손실이 생긴다. 9...a6이 더 나은 대안이었다. |  |
| AG7 1 | 0 | backed reason | 9...b5는 실수였다. 엔진이 제시한 수순에서는 이 전진 뒤 흑이 비숍을 잃어, 교환 결과 최소 2점의 물질 손실이 난다. |  |
| AG7 1 | 1 | restated | 대신 9...a6가 더 나은 선택으로 판정됐다. 성급한 ...b5가 백의 전술적 응수를 허용한 것이 이 장면의 핵심이다. |  |
| AG7 2 | 0 | backed reason | 9...b5는 실수였다. 엔진이 분석한 수순에서는 흑이 b4의 비숍을 잃는 결과가 나왔고, 9...a6가 더 나은 대안이었다. |  |
| AG7 2 | 1 | reading | b폰을 밀어 공간을 얻으려는 시도는 백의 전술적 응수를 허용했다. 이 순간부터 백의 기물 희생이 가능한 배경이 마련된다. |  |
| AG7 3 | 0 | backed reason | 9...b5는 실수였다. 엔진이 분석한 한 수순에서는 백의 나이트가 뛰어들고, 흑이 받아친 뒤 14.cxb4로 b4의 비숍을 잃는다. |  |
| AG7 3 | 1 | restated | 대안으로는 9...a6이 더 나았다. b폰을 밀어 전술적 표적을 만든 선택이 모피에게 기회를 내준 셈이다. |  |

**ply 25 (13.Rxd7)**

| trial | # | class | sentence | mark |
| --- | --- | --- | --- | --- |
| today 1 | 0 | backed reason | 13.Rxd7는 브릴리언트 수로 평가됐다. 특정 분석 라인에서는 13...Rxd7 14.Rd1 뒤 백 룩이 16.Rxd7로 흑 룩을 잡아, 라인 전체에서 순 3점 이상의 기물 이득을 얻는다. |  |
| today 2 | 0 | backed reason | 13.Rxd7은 최선수이자 브릴리언트로 판정됐습니다. 특정 라인에서 백은 룩을 내주는 제안을 하지만, 흑이 받아도 백은 버팁니다. 또 엔진이 제시한 한 변형에서는 백이 결국 d7의 흑 룩을 잡아 최소 3점의 기물 이득을 얻습니다. |  |
| today 3 | 0 | backed reason | 13.Rxd7는 브릴리언트로 평가된 최선수다. 룩을 내주는 듯한 응수도 감수하며, 엔진이 제시한 한 라인에서는 이후 16.Rxd7로 흑의 룩을 잡아 물질적 이득을 얻는다. |  |
| AG7 1 | 0 | backed reason | 13.Rxd7는 나이트를 잡으면서 흑의 a7 폰, e7 퀸, d8 룩을 동시에 겨누는 포크를 만든다. |  |
| AG7 1 | 1 | backed reason | 흑이 룩으로 받아도, 엔진 라인에서는 뒤이어 16.Rxd7로 d7의 흑 룩을 다시 잡는다. 눈앞의 룩을 내주는 듯해도 전술적 보상까지 계산한 브릴리언트 수다. |  |
| AG7 2 | 0 | backed reason | 13.Rxd7 역시 브릴리언트로 평가된 최선수다. 엔진 수순에서 이 루크의 침투는 a7폰, e7의 퀸, d8의 루크를 함께 겨누는 포크로 나타난다. |  |
| AG7 2 | 1 | backed reason | 그 수순에서는 흑 루크를 d7에서 다시 잡아 최소 3점의 물질적 이득을 얻는 결과까지 계산된다. |  |
| AG7 2 | 2 | reading | 따라서 이 루크의 진입은 단순한 교환 제안이라기보다, 흑의 주요 기물들을 한꺼번에 묶어두는 전술적 압박으로 보인다. |  |
| AG7 3 | 0 | backed reason | 13.Rxd7는 흑의 루크가 받도록 내놓은 브릴리언트 수다. 엔진 분석에서 d7의 백 룩은 a7의 폰, e7의 퀸, d8의 룩을 동시에 겨눈다. |  |
| AG7 3 | 1 | backed reason | 흑이 13...Rxd7로 받아도, 이어지는 14.Rd1 뒤 분석선은 백이 16.Rxd7로 d7의 룩을 되잡는 전개를 보여 준다. |  |
| AG7 3 | 2 | reading | 겉으로는 룩을 교환하자는 제안처럼 보이지만, d파일의 침투와 흑 퀸에 대한 압박을 묶은 계산이었다. |  |

**ply 29 (15.Bxd7+)**

| trial | # | class | sentence | mark |
| --- | --- | --- | --- | --- |
| today 1 | 0 | line | 15.Bxd7+는 실수로 평가됐다. 대신 15.Bxf6가 더 나았으며, 분석 라인은 15...gxf6 16.Bxd7+ Qxd7 17.Qb8+ Ke7로 이어진다. |  |
| today 2 | 0 | restated | 15.Bxd7+는 실수로 판정됐으며, 더 나은 대안은 15.Bxf6였습니다. 실제 수순의 특정 변형에서는 15.Bxd7+로 d7의 흑 룩을 잡아 최소 3점의 기물 이득을 얻지만, 그럼에도 더 나은 수를 놓친 장면입니다. |  |
| today 3 | 0 | line | 15.Bxd7+는 실수였다. 체크를 걸며 룩을 잡았지만, 15.Bxf6가 더 강했고 한 구체적인 라인은 15...gxf6 16.Bxd7+ Qxd7로 이어진다. |  |
| AG7 1 | 0 | restated | 15.Bxd7+는 체크를 걸며 d7의 룩을 잡지만, 이 수는 실수로 판정됐다. |  |
| AG7 1 | 1 | line | 엔진은 먼저 15.Bxf6 gxf6 16.Bxd7+ Qxd7 17.Qb8+ Ke7...로 잇는 편을 훨씬 높게 평가한다. 당장 룩을 거두기보다 흑의 수비를 더 무너뜨리는 순서를 택할 수 있었던 장면이다. |  |
| AG7 2 | 0 | line | 15.Bxd7+는 체크를 걸었지만 실수 판정을 받았다. 엔진은 15.Bxf6를 더 나은 수로 꼽았고, 이어지는 분석 수순은 ...gxf6, Bxd7+, ...Qxd7, Qb8+, ...Ke7로 전개된다. |  |
| AG7 2 | 1 | reading | 체크를 먼저 넣는 수보다 f6의 나이트를 정리하는 순서가 더 강했다. 백은 이 차이를 두고 승리의 폭을 상당히 좁혔다고 볼 수 있다. |  |
| AG7 3 | 0 | line | 15.Bxd7+는 체크를 걸며 흑의 d7 룩을 잡지만, 흑은 15...Nxd7로 비숍을 되잡는다. 엔진은 이 수를 실수로 판정했다. |  |
| AG7 3 | 1 | line | 대신 15.Bxf6! gxf6 16.Bxd7+ Qxd7 17.Qb8+로 이어지는 분석선이 더 나은 선택이었다. |  |
| AG7 3 | 2 | reading | 체크를 먼저 거는 직관적인 선택보다, f6의 나이트를 제거한 뒤 d7을 다시 정리하는 순서가 더 큰 압박을 유지했다. |  |

### rapid game 813–801

**ply 40 (20...c6)**

| trial | # | class | sentence | mark |
| --- | --- | --- | --- | --- |
| today 1 | 0 | restated | 20...c6는 실수였고, 20...Qd6가 더 나은 대안이었다. |  |
| today 2 | 0 | restated | 20...c6는 실수였다. 20...Qd6가 더 나은 대안이었다. |  |
| today 3 | 0 | restated | 20...c6는 실수였다. 20...Qd6가 더 나은 대안이었다. |  |
| AG7 1 | 0 | restated | 흑의 수는 실수로 판정됐고, 엔진은 ...Qd6을 대안으로 제시했다. |  |
| AG7 1 | 1 | reading | 흑이 퀸을 안전한 칸으로 옮겨 두었다면 백의 압박을 줄일 여지가 더 컸을 것으로 보인다. |  |
| AG7 2 | 0 | restated | 20...c6는 실수였고, 20...Qd6가 더 나은 대안이었다. |  |
| AG7 2 | 1 | reading | 폰을 움직여 중앙의 긴장을 바꾸기보다 퀸으로 대응하는 편이 더 안전했던 것으로 보인다. |  |
| AG7 3 | 0 | restated | 20...c6는 실수였고, ...Qd6가 더 나은 대안이었다. |  |
| AG7 3 | 1 | reading | 이 수 뒤 백의 평가상 우세가 크게 커졌으므로, 흑은 폰을 움직이기보다 퀸으로 맞서는 편이 나았던 장면이다. |  |

**ply 52 (26...Re8)**

| trial | # | class | sentence | mark |
| --- | --- | --- | --- | --- |
| today 1 | 0 | backed reason | 26...Re8는 블런더로, 백에게 메이트를 허용했다. 더 나은 수는 26...Bd7이었다. |  |
| today 2 | 0 | backed reason | 26...Re8는 블런더로, 특정 라인에서 백의 메이트를 허용했다. 26...Bd7가 더 나은 대안이었다. |  |
| today 3 | 0 | backed reason | 26...Re8는 블런더였다. 분석된 수순 26...Re8 27.Bxf7+ Kxf7 28.Qxh7+ Kf8 29.Qh8+에서는 메이트까지 이어진다. 26...Bd7가 더 나은 대안이었다. |  |
| AG7 1 | 0 | restated | 흑의 26...Re8은 블런더로 판정됐고, 엔진은 26...Bd7을 더 나은 방어로 평가했다. |  |
| AG7 1 | 1 | backed reason | 실전 수 뒤 엔진 수순은 27.Bxf7+ Kxf7 28.Qxh7+ Kf8 29.Qh8+로 이어지며, 이 라인에서는 백이 메이트를 강제한다. | borderline: '강제' scoped to the engine line, citing a server mate claim |
| AG7 1 | 2 | reading | 룩을 e8에 놓아 백의 공격을 막으려 한 듯하지만, 실제로는 킹 주변의 전술적 위협을 키운 결정적인 실수가 됐다. |  |
| AG7 2 | 0 | backed reason | 26...Re8는 블런더였고, 이 수순은 백에게 메이트를 허용한다. |  |
| AG7 2 | 1 | backed reason | 엔진이 제시한 메이트 수순은 27.Bxf7+ Kxf7 28.Qxh7+ Kf8 29.Qh8+ 뒤 Ng5#이다. |  |
| AG7 2 | 2 | restated | 대신 26...Bd7로 두는 것이 더 나은 방어였다고 분석됐다. |  |
| AG7 2 | 3 | reading | 흑이 룩을 e8로 옮긴 순간, f7의 비숍 희생을 동반한 공격이 결정적으로 이어지는 국면이 됐다. |  |
| AG7 3 | 0 | backed reason | 26...Re8는 블런더였고, 엔진이 제시한 26...Re8 27.Bxf7+ Kxf7 28.Qxh7+ Kf8 29.Qh8+ 수순에서는 백이 메이트를 강제할 수 있었다. | borderline: '강제' scoped to the engine line, citing a server mate claim |
| AG7 3 | 1 | reading | 대신 ...Bd7이 더 나은 방어였다는 분석과 나란히 보면, 룩을 옮긴 수가 백의 공격을 막지 못한 중대한 전환점이었다. |  |

**ply 53 (27.Bxf7+)**

| trial | # | class | sentence | mark |
| --- | --- | --- | --- | --- |
| today 1 | 0 | backed reason | 27.Bxf7+는 최선이자 브릴리언트로 판정됐다. 27...Kxf7로 받아도 엔진 라인에서는 백의 메이트 공격이 이어진다. |  |
| today 2 |  | — | (not commented) |  |
| today 3 | 0 | restated | 27.Bxf7+는 최선이자 브릴리언트로 판정됐다. 비숍을 내주는 수다. |  |
| AG7 1 | 0 | restated | 백의 27.Bxf7+는 최선이자 브릴리언트로 판정된 체크다. |  |
| AG7 1 | 1 | backed reason | 이 수는 f7의 비숍을 내놓는 수로, 흑이 27...Kxf7로 받는 엔진 수순에서는 28.Qxh7+ Kf8 29.Qh8+ Kf7 뒤에 메이트가 이어진다. |  |
| AG7 1 | 2 | backed reason | 실전처럼 27...Nxf7로 비숍을 잡으면 28.Rxe8#가 성립해, 희생의 핵심은 물질이 아니라 킹을 향한 강제 공격에 있다. | borderline: '강제' scoped to the engine line, citing a server mate claim |
| AG7 2 |  | — | (not commented) |  |
| AG7 3 |  | — | (not commented) |  |

**ply 54 (27...Nxf7)**

| trial | # | class | sentence | mark |
| --- | --- | --- | --- | --- |
| today 1 | 0 | line | 27...Nxf7는 실수였고, 28.Rxe8#를 허용했다. 대신 27...Kxf7로 두는 편이 나았다. |  |
| today 2 | 0 | backed reason | 27...Nxf7는 실수였다. 27...Nxf7에 28.Rxe8#로 즉시 메이트가 가능했고, 27...Kxf7가 더 나은 대안이었다. |  |
| today 3 | 0 | line | 27...Nxf7는 실수였다. 28.Rxe8#를 허용하며, 27...Kxf7가 더 나은 대안이었다. |  |
| AG7 1 | 0 | restated | 흑의 27...Nxf7는 실수로 판정됐다. 체크에 대응해 f7의 비숍을 잡았지만, 엔진은 27...Kxf7이 더 나았다고 봤다. |  |
| AG7 1 | 1 | backed reason | 실전 수는 28.Rxe8#를 허용해 즉시 메이트로 끝난다. |  |
| AG7 2 | 0 | backed reason | 27...Nxf7는 실수였고, 28.Rxe8#으로 한 수 만에 메이트가 된다. |  |
| AG7 2 | 1 | backed reason | 흑은 체크에 맞서 f7의 비숍을 잡는 방식으로 응수했지만, 그 선택이 룩의 메이트를 허용했다. |  |
| AG7 2 | 2 | restated | 엔진은 27...Kxf7을 더 나은 방어로 제시했다. |  |
| AG7 2 | 3 | reading | 비숍을 잡는 응수는 자연스러워 보일 수 있지만, 이때는 킹으로 잡아야 즉시 메이트를 피할 수 있었다. |  |
| AG7 3 | 0 | line | 27...Nxf7는 실수였고, 28.Rxe8#를 허용했다. 엔진은 대신 ...Kxf7을 더 나은 응수로 꼽았다. |  |
| AG7 3 | 1 | reading | 체크에 대응해 비숍을 잡았지만, 그 순간 e8의 룩이 들어오는 메이트를 막지 못했다. |  |

