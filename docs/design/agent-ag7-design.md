# Agent — AG7-D design: commentary guidance v2, and two refusals that mislead

Status: **rev. 1 — for independent review**. Date: 2026-10-17. Base: `main @ cbbd7da` (AG6b merged).
Inputs: [`agent-mcp-design.md`](agent-mcp-design.md) (AG-D: §4 propositions and uses, §5.3 the
sentence check, §6 the prompts, §10 build identity),
[`agent-ag5-design.md`](agent-ag5-design.md) (AG5-D: the guides as resources, G8 the guidance
version), [`agent-ag6-design.md`](agent-ag6-design.md) (AG6-D: digests, `detail`, `items`); trials
in HIMARI v3 (2026-10-17, §0).

The owner's complaint after AG5 was deployed: an agent's commentary reads like Calliope's own
explanation in Korean — the grade, "a better move was X", one sentence a moment — not like a
commentator talking through the game. This design changes what the commentary guide asks for
(§2, §3) and fixes two answers of the server that send agents the wrong way (§4, §5). It changes
no tool, proposition, sentence class or check (§6).

## 0. The trials (2026-10-17)

HIMARI v3 (`main @ 3120ef9`) drove one conversation per trial against Calliope `main @ cbbd7da`
over stdio in HIMARI's server sandbox (one shared process, an empty data directory). Variants of
the guidance and the check were switched by environment variables in a scratch copy of the
server, never in `main`. One user message per trial: write and save the commentary of one ply
(`1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. d3 h6 *`, ply 10), or analyse a whole game and comment
its important moments (the Opera Game, 33 plies, 6 moments; the rapid game
`tests/reasoning/fixtures/chesscom_rapid_813_801.pgn`, 55 plies, 8–10 moments). Models through
OpenRouter: `openai/gpt-6-luna` (HIMARI's default, the deployment's), `anthropic/claude-haiku-5.5`,
`anthropic/claude-sonnet-5.5`. 78 trials, about $3.5 in all.

Measured from the stored commentaries: characters of all sentences, of `interpretation`
sentences, sentences citing a board fact or an explored line (`attack`, `defence`, `pin`,
`pattern`, `exposed`, `check`, `legal_moves`, `material`, `explored_line`), tool calls, refusals,
cost at the published prices. Facts in the sentences were checked by hand against the board.

### 0.1 What was tried

| Trial set | Variants | Result |
| --- | --- | --- |
| 1 (12 trials, 1 each) | today's guide; a guide with content criteria (situation, intent, problem, the better move's idea, the game's flow; lengths; one interpretation at least) — "B"; B with interpretation sentences allowed the occupied squares and legal moves of the subject's positions without a citation — "C" | luna, Opera: 479 → 854 (B) → 1,213 characters (B+C); one sentence a moment with today's guide. Sonnet B+C 1,691, concrete and correct. luna and Haiku B+C wrote wrong board relations C let through ("b5 aims at the c3 knight": it attacks the c4 bishop). |
| 2 (22 trials) | B′ (decide freely, then find evidence for each point, drop what has none), Calliope's own sentences removed from `ply` / `judge_move` / `detail` (`text`, `says`, `segments`), the claims removed too, ± C | No `explore` and no `facts` in 22 trials (one `judge_move`). Removing Calliope's sentences changed nothing: the agents paraphrased the engine lines instead. "Drop what has no evidence" shortened the commentary (Sonnet 1,691 → 927–1,115) instead of sending it to the tools. |
| 3 (21 trials) | B′ with a table of twelve kinds of commentator's remark, each with its situation, its shape and the tool and proposition that back it, three examples from another game; ± the drop rule | Sonnet without the drop rule: 1,527 characters, more kinds (other candidates' scores, the board's assessment, a lesson) and the first cited `explore`. luna unchanged (715–957). Haiku between (1,258, vague in places). |
| pre-check (22 trials) | **the guide of Appendix A** (B + the table + no drop rule + "Calliope's `text`/`says` are not to be translated"), Calliope's sentences kept, no C — against today's guide, same server otherwise | §0.2 |

The commentary types of the table come from three annotated sources (Wikipedia's notes on the
Opera Game, the Lichess study "Morphy's Opera Game", Capablanca's *Chess Fundamentals* (1921), game
13): the purpose of a move, a move doing two things, a threat or a double attack, the refutation
of a mistake, the better move compared, why the natural move fails, a forced move, the position's
assessment, a plan, a difference of judgement, the game's flow, a principle. Human notes mix
several of these on one move; the agents wrote only the refutation and the comparison — the two
Calliope's own explanation is made of.

### 0.2 The pre-check: Appendix A against today's guide (luna, 3 trials each unless noted)

| Task | Today's guide | Appendix A |
| --- | --- | --- |
| Opera Game | 661 characters (556–776), 143 interpretation | 1,294 (1,096–1,431), 412 interpretation; 8 sentences cite `attack` / `pin` (the agent called `facts` 8 times) |
| Rapid game 813–801 | 495 (396–587), 0 interpretation | 1,489 (1,385–1,590), 755 interpretation; 18 of 48 interpretation sentences general ("the timing mattered") |
| Rapid game, Appendix A as given (after the line on general sentences, §3) | — | 1,456 (1,226–1,602); 5 of 33 interpretation sentences general |
| One ply (2 trials) | 117 | 179 |
| Rapid game, Sonnet (1 trial) | 1,039 | 1,220 |
| Cost, Opera, luna | $0.007 | $0.014 |

Without C a sentence that names a square needs a proposition that holds it, and with the table the
agent went and got one: "d7의 흑 나이트는 b5의 비숍에 의해 킹 쪽으로 핀에 걸려 있고, 백 룩도 그 나이트를 공격하고
있었다" cites a `pin` and an `attack`. That is the guide working as the check intends; C is not
needed for it (§6).

Refusals stayed at one or two a trial. The two most frequent across all trials are the server's
own doing (§4, §5): a claim cited with the wrong `use` (28 in trial set 2 alone; `function`, the
claim's role, written as its use 10 times in the pre-check), and `...d6` refused as a token.

### 0.3 What the trials do not show

Agents of every model left `explore` and `facts` alone unless a sentence could not pass without
them: 78 trials, one cited explored line. The guide cannot make an agent verify a "why" it
can pass without; the real reason for 5...h6 (after 5...Bc5 the same 6.Bxc6 dxc6 7.Nxe5 meets
7...Qd4) was found in none. Facts the server offers with the ply are the way to that (next design,
§8). The trials are few per cell (1–3), two of the three games, and checked by hand; the Opera Game
is famous enough that a model may remember notes on it, which is why the rapid game was added.

## 1. Decisions

| # | Decision |
| --- | --- |
| H1 | **A new prompt version**, `agent/prompts/commentary_ko_v2.md` (prompt id `prompt.commentary_ko_v2`, Appendix A), served by the prompt `calliope_commentary` and the resource `calliope://guides/commentary_ko` (URIs and names unchanged). `commentary_ko_v1.md` stays in the repository as versioned data, no longer served, so the digest an older commentary's `agent_build` carries still names a file. |
| H2 | **What the guide asks for** (§2): a commentator's story of the move from Calliope's data; Calliope's `text` and `says` are its own explanation, already on the board, and not to be translated; lengths (4–7 sentences for a key moment, 2–3 otherwise); every reading kept as an `interpretation` with the nearest evidence, worded as a reading — never dropped; no general sentences that fit any game. |
| H3 | **The table of remarks and their evidence** (§3): twelve kinds, each with when it fits, its shape and the tool and proposition that back it; three examples from another game; a key moment carries at least one of the purpose, the threat, why the natural move fails, or the assessment. |
| H4 | **A refused `use` says which uses the claim takes** (§4): `expected` lists them instead of the claim's status. |
| H5 | **`...d6` is Black's move** (§5): a move written with three dots and no number reads as a move of Black's; `.d6` stays a violation. |
| H6 | **The guidance version**: `agent_guidance_v4`, pinned to the new digest (AG5-D G8); the agent registry gains `prompt.commentary_ko_v2` in place of `prompt.commentary_ko_v1` and the amended `token_rule.move` statement, so `agent_definitions_v1`'s digest changes. `TOOLS_VERSION` stays `agent_tools_v5`. |
| H7 | **Not changed** (§6): C (interpretation sentences stay checked like sourced ones), the digests (Calliope's `text` and `says` stay), the instructions, the check guide `check_ko_v1`, tools and their arguments, propositions and uses, sentence classes, `commentary_check_v1`, the viewer, the reasoning build and every cache key. |

## 2. What the guide asks for

Today's guide (`commentary_ko_v1`) has eight numbered rules, seven of them about what not to
write, and no word on what a commentary contains. Appendix A starts from the job: Calliope gives
data and tools, the agent writes the story of the move. The working order is four steps — read the
board (`ply`: grade, evaluation, best move, both lines, the FENs, the claims), choose two to four
kinds of remark (§3), check them with the tools, write — and two rules carry the trials' lessons:

- **Keep readings.** A reading the agent could not fully check is written as an `interpretation`
  sentence citing the nearest evidence, in the words of a reading ("~로 보인다"). Trial set 2 asked
  to drop such points and got shorter commentaries, not checked ones.
- **No general sentences.** An interpretation reaches something on the board — a piece, a square,
  a line. "기회를 놓쳤다", "흐름이 넘어갔다" fit any game; a move with nothing concrete to say gets a
  short commentary and the room goes to the key moments. The pre-check's general sentences fell
  from 18 of 48 to 5 of 33 with this line.

The rules that hold today (proposition form, a judgement of the subject, notation, reading claims:
ATTRIBUTED, `specific_line`, patterns, INCONCLUSIVE and REFUTED, the agent's own lines) stay, in
one short list. Two lines are new, from the refusals of §0.2: which `use` fits which claim (line
fact by default; `comparison` for a comparison, `result` for a consequence; never the role's name),
and that `cites` holds the ids of the agent's own propositions, not a claim's template.

## 3. The table of remarks

Appendix A's table names, for each of twelve kinds of remark, when it fits, its shape in Korean and
the evidence: the tool to call and the proposition kind to cite, with positions written as `{"ply":
n, "at": "before" | "after"}`. It says that `explore` without `search` spends no engine budget. The
three examples paraphrase Capablanca's notes to a different game (*Chess Fundamentals*, game 13;
public domain), so no example tells an agent the answer to a game it is asked about. Kinds 11–13
of the sources (motives and style, openings and history, questions to the reader, exclamations)
are left out: Calliope has nothing to back them, and the trials gain nothing by inviting them.

## 4. A refused `use`

`Verifier._claim` refuses a `use` the claim does not take with `Refused("use", problem,
claim["status"])`: its `expected` is the claim's status, `"supported"`. Agents read `expected` as
the value to write and submitted `use: "supported"`, refused again (`no use 'supported'`). AG7
answers `expected` with the uses the claim takes — every `u` of `USES` for which `_use(claim, u,
source)` is `None`, in `USES`' order — for every refusal of the `use` field after the field is a
known use (an unknown use already lists `USES`). The problem text and every other field are
unchanged; what is accepted is unchanged.

## 5. `...d6`

S3's move token is `(\d+(\.|\.\.\.) ?)?SAN`: three dots without a number are not part of a move, so
`...d6` is neither a move nor a square and is refused (`'...d6' is neither a move, a score, a mate,
a square nor a cited number`). Korean commentary writes Black's moves this way; it was refused 26 times in
seven trials, and the agents rewrote sentences around it. AG7 reads `...` without a number as Black's move:
`(\d+)?(\.|\.\.\.) ?` before the SAN, then

- a number and dots: as today (the number is the move's fullmove number, `...` exactly for Black);
- `...` without a number: the move must be Black's at its position (a cited move of White's is
  refused as not a move of the cited propositions);
- `.` without a number: not a move — the token is refused as today;
- no number and no dots: as today (a bare pawn push is a square).

The capture, check and mate marks hold as today (AM2). `token_rule.move`'s statement says so. The
split rule is unchanged (`...` alone, apart from the move, still reads as nothing and the move
after it as a bare SAN).

## 6. Not changed, and why

- **C.** With C the strong model wrote the best commentary of the trials, and the small models wrote
  board relations that were wrong and passed (§0.1). Without it, Appendix A got the small model to
  fetch the facts it needed (§0.2). C stays out; the next design gives the agent the board's facts
  with the ply, after which C is decided again on measurements.
- **Calliope's sentences in the digests.** Removing them changed nothing in trial set 2; they cost
  the agent little and tell it what Calliope already shows. The guide says not to translate them.
- **The instructions and the check guide.** The pre-check ran with today's instructions and
  `check_ko_v1`; their rules are the rules Appendix A keeps.

## 7. Implementation (packet AG7)

- `agent/prompts/commentary_ko_v2.md` (Appendix A, byte for byte); `build.PROMPTS` =
  `("commentary_ko_v2", "check_ko_v1")`; the prompt `calliope_commentary` and the resource
  `calliope://guides/commentary_ko` render it (`GUIDE_URIS` keyed by the new name); `commentary_ko_v1.md`
  kept, unserved.
- `agent/definitions.py`: `prompt.commentary_ko_v2` replaces `prompt.commentary_ko_v1` (statement
  unchanged); `token_rule.move` amended (§5); `GUIDANCE_VERSION = "agent_guidance_v4"`.
- `agent/propositions.py`: §4. `agent/sentences.py`: §5.
- AG-D gains AM11 (§5.3 move token, §6 the prompt version; this design).

Tests:

- the guidance pin: `agent_guidance_v4` pinned to the new digest; `agent_build()["prompts"]` names
  `commentary_ko_v2` with its file's digest;
- the resource and the prompt render `commentary_ko_v2.md` (resource with `<game>`/`<ply>`, the
  prompt with its arguments), byte-equal but for the target;
- `definitions(ids=["prompt.commentary_ko_v2"])` finds it; `prompt.commentary_ko_v1` is missing;
- §4: a comparison claim cited as `result` is refused with `expected == ["line_fact",
  "comparison"]` (or what `_use` gives for that claim); an inconclusive claim cited as `result`
  lists `["uncertain"]`; a refuted claim `["not_the_case"]`; acceptance unchanged for every use the
  existing tests accept;
- §5: `...d6`, `...Nf6`, `...exd5`, `...Qxb2` accepted when cited and Black's; `...e4` refused when
  the cited `e4` is White's; `.d6` refused; `1...d6`, `d6`, `1.e4` as today; `...Rxe8+` refused when
  the move is not a check; the existing S3 tests pass unchanged.

Acceptance trial (recorded in the implementation document): §0.2's setup with AG7's server in place
of the scratch copy — luna, 3 trials each on the Opera Game and the rapid game, today's guide
(`main @ cbbd7da`) against AG7. AG7 passes when, on both games, its average length is at least 1.5
times today's, at most 20% of its interpretation sentences are general (no piece, square or move),
its refusals a trial are no more than today's, and a hand check of three moments a game finds no
error that today's guide's commentary on the same moments does not have.

## 8. Next

The board's facts with the ply — the pins, double attacks, sole defenders and loose pieces of the
positions before and after the move, and the same reply after the best move and the played one — as
citable items in the digest (the "why" the trials never reached, §0.3). After it: C measured again,
and whether a submission of a key moment must cite a board fact.

## 9. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Keep `commentary_ko_v1.md` in the repository, unserved (H1)? | Yes: older commentaries name its digest. |
| Q2 | The lengths (4–7 sentences for a key moment, 2–3 otherwise; 12 is the check's maximum)? | As in Appendix A. |

## Appendix A — `agent/prompts/commentary_ko_v2.md`

The file as it is to be committed (the double braces are `str.format`'s, as in v1):

````markdown
# Calliope 해설 작성 (prompt.commentary_ko_v2)

대상: 게임 {game}, 수 {ply}.

## 당신의 일

당신은 체스 해설가입니다. Calliope는 등급, 평가, 엔진 라인, 클레임 같은 데이터와 그것을 확인하는 도구를 줍니다. `ply`의 `text`와 클레임의 `says`는 Calliope가 만든 기본 해설이고, 판에 이미 표시됩니다. **그것을 한국어로 옮기는 해설은 실패입니다.** 데이터를 재료로 삼아, 사람 해설가처럼 이 수의 이야기를 쓰세요.

## 순서

1. **판을 읽습니다.** `ply`로 등급, 평가, 최선수, 둔 수와 최선수의 라인, 수 전후 FEN, 클레임을 받습니다. FEN과 라인을 직접 읽고 무엇을 말할지 정하세요.
2. **말할 것을 고릅니다.** 아래 표에서 이 장면에 맞는 유형을 2~4개 고르세요.
3. **근거를 확인합니다.** 표의 도구로 확인하고, 확인한 것을 명제로 만듭니다.
4. **씁니다.** 확인한 말은 sourced 문장으로 쓰고 그 명제를 인용합니다. 의도, 계획, 흐름, 교훈 같은 당신의 읽기는 interpretation 문장으로 쓰고 가장 가까운 근거를 인용합니다. 근거를 다 찾지 못한 읽기도 버리지 말고, 단정 대신 "~로 보인다", "~했을 것이다"처럼 쓰세요.

분량: 핵심 장면은 4~7문장, 덜 중요한 수는 2~3문장. 등급을 말하는 문장은 하나면 충분합니다. 나머지는 "왜"와 "어떻게"에 쓰세요. **짧은 해설은 실패입니다.**

해석 문장은 판의 구체적인 것(기물, 칸, 수순)에 닿아야 합니다. "기회를 놓쳤다", "흐름이 넘어갔다", "타이밍이 중요했다"처럼 어느 대국에나 맞는 일반론만 있는 문장은 분량을 채울 뿐이니 쓰지 마세요. 구체적으로 말할 것이 없는 수는 짧게 쓰고, 그 분량을 핵심 장면에 쓰세요.

## 해설가가 하는 말: 상황별 주장과 근거

위치는 `{{"ply": n, "at": "before" | "after"}}`(그 수를 두기 전/후)입니다.

| 유형 | 언제 | 주장의 모양 | 근거 (도구 → 명제) |
|---|---|---|---|
| 1. 수의 목적 | 모든 수, 특히 전개·공격 | "이 수는 ○를 공격한다 / 체크·위협을 만든다" | `facts(position: 수 뒤)` → `attack`, `check`, `pin` |
| 2. 다목적 | 한 수가 둘 이상을 할 때 | "○를 하면서 동시에 △를 막는다" | `facts` 두 가지 + 막힌 수를 `explore`로 두어 실패를 보임 → `explored_line`, `material` |
| 3. 위협·이중 공격 | 상대가 막아야 할 것이 생길 때 | "○와 △를 동시에 노린다. 막지 않으면 □" | `facts` → `pattern`(multi_target_attacks), `explore(position: 수 뒤, moves: [아무 수, 위협 수])` |
| 4. 실수의 반박 | 실수·블런더 | "이 수는 □에 걸린다: 상대가 ○를 두면 △" | 둔 수의 엔진 라인 → `engine_line`, `material`; 또는 `explore`로 반박 수순 |
| 5. 더 나은 수와 비교 | 최선수와 차이가 클 때 | "○였다면, 같은 응수 △에 □가 된다" | 최선수 라인 → `engine_line`; `explore(position: 수 전, moves: [최선수, 같은 응수])`; `judge_move` |
| 6. 왜 자연스러운 수가 아닌가 | 그럴듯한 다른 수가 있을 때 | "○는 안 된다. △ 때문이다" | `judge_move(position: 수 전, move: ○)` 또는 `explore(moves: [○, △])` → `material` |
| 7. 강제·유일한 수 | 다른 수가 다 나쁠 때 | "사실상 유일한 수다. ○를 두면 △" | 다른 후보의 점수 → `engine_score`; `judge_move` |
| 8. 국면 평가 | 장면의 시작, 큰 변화 뒤 | "○의 기물들이 묶여 있다 / 킹이 중앙에 남아 있다" | `facts(position)` → `pin`, `defence`, `pattern`(sole_defenders), `exposed` |
| 9. 계획 | 여러 수에 걸친 의도 | "○를 거쳐 △를 노린다" | `explore`로 계획 수순을 두어 끝 국면의 `facts` |
| 10. 판단의 차이 | 비슷해 보이는 선택지 | "○를 지키려 했지만 △를 막는 것이 더 중요했다" | 두 수의 `judge_move`/점수 비교 + 막지 못한 △의 `explore` |
| 11. 흐름 | 전환점, 결정타 | "앞의 ○가 여기서 대가를 치른다 / 이 수부터 □" | 앞뒤 장면의 판정과 평가 → interpretation |
| 12. 원칙·교훈 | 원칙에 맞거나 어긋날 때 | "전개보다 폰을 먼저 움직인 대가다" | 그 국면의 사실(전개되지 않은 기물, 캐슬링 전 킹)을 `facts`로 → interpretation |

예시(다른 대국의 해설 방식):
- 판단의 차이(10): "백은 나이트의 핀을 유지하려고 비숍을 물렸지만, 흑의 캐슬링을 막는 것이 더 중요했다. 다른 대각선으로 갔다면 그것을 막을 수 있었다." → 두 비숍 후퇴의 판정 비교 + 캐슬링이 가능한지 국면 사실.
- 다목적(2): "나이트가 물러나 비숍의 대각선을 열고, 동시에 백의 e폰 전진을 막는다. 전진하면 나이트가 비숍을 잡고 폰을 얻는다." → 대각선의 `attack` + 폰 전진 수순의 `explore`와 `material`.
- 왜 자연스러운 수가 아닌가(6): "나이트를 e7로 보내는 수는 안 된다. Nd5가 있기 때문이다." → `explore(moves: [Ne7, Nd5])`.

나쁜 해설은 유형 4·5만 씁니다("실수다. ○가 더 나았다"). 핵심 장면에서는 유형 1·3·6·8 중 적어도 하나를 넣으세요. `explore`는 `search` 없이 두면 엔진 예산을 쓰지 않습니다.

## 명제와 표기

- 명제는 `{{"id", "kind", ...}}`입니다. 판정·클레임은 핸들만으로 씁니다: `{{"id": "p1", "kind": "judgement", "judgement": "<j 핸들>"}}`, `{{"id": "p2", "kind": "claim", "claim": "<c 핸들>", "use": "line_fact"}}`. 다른 종류의 필드는 `definitions`에서 `proposition.<kind>`로 찾습니다. 이 수 자신의 판정을 인용한 judgement 명제가 하나 있어야 합니다.
- 클레임의 `use`는 다음 값 중 하나입니다: `line_fact`(그 라인에서 일어난 일, 대부분 이것), `comparison`(role이 comparison인 클레임), `result`(role이 consequence인 클레임), `mechanism`, `associated`, `uncertain`, `not_the_case`. role이 function이나 mechanism인 클레임은 보통 `line_fact`입니다. role 이름을 use로 쓰지 마세요. 거부되면 응답의 `expected`에 그 클레임에 쓸 수 있는 값이 나옵니다.
- 문장의 `cites`에는 당신이 만든 명제의 `id`만 씁니다. 클레임의 이름이나 템플릿은 id가 아닙니다.
- 문장의 수·평가치·칸·숫자는 인용한 명제에 있어야 합니다. 라인에 나온 수를 쓰려면 그 라인 명제를 인용하세요. 판의 칸을 말하려면(예: "f7을 겨눈다") 그 칸을 담은 `facts` 명제를 인용하세요.
- 수는 SAN(17.Ne3, 17...Rxe3, 흑의 수는 ...Rxe3도 됨), 평가치는 백 기준(+0.38, -1.20)이고 부호는 숫자에 붙입니다. 숫자 앞에 대시를 두지 마세요. 검사를 피하려고 숫자를 한글로 쓰지 마세요.
- 클레임 읽기: ATTRIBUTED가 실패한 득실은 이 수의 성과가 아닙니다. `specific_line`은 그 라인에서만 성립합니다. 패턴은 배치일 뿐 통하는 전술이 아닙니다. INCONCLUSIVE·REFUTED는 이유로 쓰지 않습니다. 직접 둔 라인(by: agent)을 엔진의 라인이라고 쓰지 않습니다.

## 제출

`submit_commentary`로 제출합니다(문장: `{{"text", "class": "sourced" | "interpretation", "cites": [명제 id]}}`, 한 해설에 12문장까지). 여러 수는 `items`로 한 번에 보냅니다. 거부되면 표시된 곳만 고쳐 다시 보냅니다. 저장한 뒤 `show_game`으로 판을 보여 주고, 채팅에는 짧은 요약만 씁니다.

대국 전체를 해설할 때는 중요한 장면(moments)마다 위의 기준으로 쓰고, 장면끼리 이어지게 하세요(앞 장면의 실수가 다음 장면에서 어떻게 대가를 치르는지). 첫 장면의 해설에는 오프닝과 초반 구도를 한두 문장으로 넣으세요.

용어는 `calliope://glossary/ko`를 따릅니다. 예산은 응답의 `budget_left`에 있고, 거부되면 `retry_after_seconds` 뒤에 다시 시도합니다. 게임 id는 계속 같습니다. 핸들이 만료되면 `ply`·`facts`·`explore`로 다시 읽습니다.
````
