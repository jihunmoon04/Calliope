# Agent — AG7-D design: commentary guidance v2, and two refusals that mislead

Status: **rev. 2 — independent review of rev. 1 (`968e62c`) NOT_READY (B1–B3; N1, N2) applied (§10); the owner chose the review's direction after a trial of it (§0.3)**. Date: 2026-10-17. Base: `main @ cbbd7da` (AG6b merged).
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
`anthropic/claude-sonnet-5.5`. 85 trials, about $3.9 in all (trial set 2 counts the one run that
checked the scratch server's switches; review count note).

Measured from the stored commentaries: characters of all sentences, of `interpretation`
sentences, sentences citing a board fact or an explored line (`attack`, `defence`, `pin`,
`pattern`, `exposed`, `check`, `legal_moves`, `material`, `explored_line`), tool calls, refusals,
cost at the published prices. Facts in the sentences were checked by hand against the board.

### 0.1 What was tried

| Trial set | Variants | Result |
| --- | --- | --- |
| 1 (12 trials, 1 each) | today's guide; a guide with content criteria (situation, intent, problem, the better move's idea, the game's flow; lengths; one interpretation at least) — "B"; B with interpretation sentences allowed the occupied squares and legal moves of the subject's positions without a citation — "C" | luna, Opera: 479 → 854 (B) → 1,213 characters (B+C); one sentence a moment with today's guide. Sonnet B+C 1,691, concrete and correct. luna and Haiku B+C wrote wrong board relations C let through ("b5 aims at the c3 knight": it attacks the c4 bishop). |
| 2 (23 trials) | B′ (decide freely, then find evidence for each point, drop what has none), Calliope's own sentences removed from `ply` / `judge_move` / `detail` (`text`, `says`, `segments`), the claims removed too, ± C | No `explore` and no `facts` in 23 trials (one `judge_move`). Removing Calliope's sentences changed nothing: the agents paraphrased the engine lines instead. "Drop what has no evidence" shortened the commentary (Sonnet 1,691 → 927–1,115) instead of sending it to the tools. |
| 3 (21 trials) | B′ with a table of twelve kinds of commentator's remark, each with its situation, its shape and the tool and proposition that back it, three examples from another game; ± the drop rule | Sonnet without the drop rule: 1,527 characters, more kinds (other candidates' scores, the board's assessment, a lesson) and the first cited `explore`. luna unchanged (715–957). Haiku between (1,258, vague in places). |
| pre-check (22 trials) | rev. 1's guide (B + the table + readings always kept + "Calliope's `text`/`says` are not to be translated"), Calliope's sentences kept, no C — against today's guide, same server otherwise | §0.2 |
| review trial (7 trials) | **Appendix A's guide** (the review's B1, B2, N1 and Q2 applied to rev. 1's guide), same setup | §0.3 |

The commentary types of the table come from three annotated sources (Wikipedia's notes on the
Opera Game, the Lichess study "Morphy's Opera Game", Capablanca's *Chess Fundamentals* (1921), game
13): the purpose of a move, a move doing two things, a threat or a double attack, the refutation
of a mistake, the better move compared, why the natural move fails, a forced move, the position's
assessment, a plan, a difference of judgement, the game's flow, a principle. Human notes mix
several of these on one move; the agents wrote only the refutation and the comparison — the two
Calliope's own explanation is made of.

### 0.2 The pre-check: rev. 1's guide against today's guide (luna, 3 trials each unless noted)

| Task | Today's guide | rev. 1's guide |
| --- | --- | --- |
| Opera Game | 661 characters (556–776), 143 interpretation | 1,294 (1,096–1,431), 412 interpretation; 8 sentences cite `attack` / `pin` (the agent called `facts` 8 times) |
| Rapid game 813–801 | 495 (396–587), 0 interpretation | 1,489 (1,385–1,590), 755 interpretation; 18 of 48 interpretation sentences general ("the timing mattered") |
| Rapid game, with the line on general sentences (§2) | — | 1,456 (1,226–1,602); 5 of 33 interpretation sentences general |
| One ply (2 trials) | 117 | 179 |
| Rapid game, Sonnet (1 trial) | 1,039 | 1,220 |
| Cost, Opera, luna | $0.007 | $0.014 |

Without C a sentence that names a square needs a proposition that holds it, and with the table the
agent went and got one (rev. 1's guide, Opera Game): "d7의 흑 나이트는 b5의 비숍에 의해 킹 쪽으로 핀에 걸려 있고, 백 룩도 그 나이트를 공격하고
있었다" cites a `pin` and an `attack`. That is the guide working as the check intends; C is not
needed for it (§6).

Refusals stayed at one or two a trial. The two most frequent across all trials are the server's
own doing (§4, §5): a claim cited with the wrong `use` (28 in trial set 2 alone; `function`, the
claim's role, written as its use 10 times in the pre-check), and `...d6` refused as a token.

### 0.3 The review trial: Appendix A (luna, 3 trials each; Sonnet 1)

The review (§10) asked that readings be kept only where they do not contradict their evidence, that
concrete facts and causes be checked or left out, and that the table say what each piece of evidence
proves. Appendix A does so; the owner asked for a quick trial before choosing.

| Task | Today's guide | rev. 1's guide | Appendix A |
| --- | --- | --- | --- |
| Opera Game | 661 | 1,294 | 878 (789–966); 7 sentences cite `attack` / `pin` |
| Rapid game | 495 | 1,456 | 1,002 (783–1,135) |
| Rapid game, Sonnet | 1,039 | 1,220 | 1,257; more cited engine scores |

A hand check of six fixed moments (Opera 9...b5, 13.Rxd7, 15.Bxd7+; rapid 20...c6, 26...Re8,
27.Bxf7+; the second trial of each guide) found no factual error in any of the three guides. Reasons
backed by a cited board fact: today's guide 0 of 11 sentences, rev. 1's 2 of 23, Appendix A's 2 of
18 — all on the Opera Game ("d7에 들어간 백 룩은 흑의 퀸 e7과 룩 d8을 동시에 공격한다", two `attack`s;
"흑 룩 d7은 b5 비숍에 핀되어 있었고", a `pin`). On the rapid game no guide got a backed reason:
rev. 1's narrated the engine lines, Appendix A's was shorter and vaguer. Appendix A cut what was
loose, not what was checked. Sonnet still wrote one forced result as a reading ("흑의 어떤 응수에든
메이트가 남도록 짜인 수"), which the guide forbids and the check cannot see.

Six of luna's 25 `facts` calls failed: it passed the table's proposition kinds as families
(`families: ["attack", "check"]`). Appendix A now says which family holds which kind (§3); not yet
re-measured — the acceptance trial (§7) does.

### 0.4 What the trials do not show

Agents of every model left `explore` and `facts` alone unless a sentence could not pass without
them: 85 trials, one cited explored line. The guide cannot make an agent verify a "why" it
can pass without; the real reason for 5...h6 (after 5...Bc5 the same 6.Bxc6 dxc6 7.Nxe5 meets
7...Qd4) was found in none. Facts the server offers with the ply are the way to that (next design,
§8). The trials are few per cell (1–3), two of the three games, and checked by hand; the Opera Game
is famous enough that a model may remember notes on it, which is why the rapid game was added.

## 1. Decisions

| # | Decision |
| --- | --- |
| H1 | **A new prompt version**, `agent/prompts/commentary_ko_v2.md` (prompt id `prompt.commentary_ko_v2`, Appendix A), served by the prompt `calliope_commentary` and the resource `calliope://guides/commentary_ko` (URIs and names unchanged). `commentary_ko_v1.md` stays in the repository as versioned data, no longer served, so the digest an older commentary's `agent_build` carries still names a file. |
| H2 | **What the guide asks for** (§2): a commentator's story of the move from Calliope's data; Calliope's `text` and `says` are its own explanation, already on the board, and not to be translated; three kinds of sentence — checked facts (`sourced`), judgements and assessments (`interpretation`, never contradicting their evidence, worded as readings), and concrete facts or causes, which are checked and sourced or left out, never passed off as readings; lengths advised, not required (4–7 sentences for a key moment, 2–3 otherwise; shorter when little is checked); no general sentences that fit any game. |
| H3 | **The table of remarks and their evidence** (§3): twelve kinds, each with the fact to observe (tool → proposition), what to check further, what may be said once checked and what may be said before; the strength of evidence named — a configuration, a possible line, a forced result; `after_reply` for the comparison; which `facts` family holds which proposition kind; three examples from another game; a key moment carries one checked remark of the purpose, the threat, why the natural move fails, or the assessment. |
| H4 | **A refused `use` says which uses the claim takes** (§4): `expected` lists them instead of the claim's status. |
| H5 | **`...d6` is Black's move** (§5): a move written with three dots and no number reads as a move of Black's; one dot without a number is no move, in the pattern itself. |
| H6 | **The guidance version**: `agent_guidance_v4`, pinned to the new digest (AG5-D G8); the agent registry gains `prompt.commentary_ko_v2` in place of `prompt.commentary_ko_v1` and the amended `token_rule.move` statement, so `agent_definitions_v1`'s digest changes. `TOOLS_VERSION` stays `agent_tools_v5`. |
| H7 | **Not changed** (§6): C (interpretation sentences stay checked like sourced ones), the digests (Calliope's `text` and `says` stay), the instructions, the check guide `check_ko_v1`, tools and their arguments, propositions and uses, sentence classes, `commentary_check_v1`, the viewer, the reasoning build and every cache key. |

## 2. What the guide asks for

Today's guide (`commentary_ko_v1`) has eight numbered rules, seven of them about what not to
write, and no word on what a commentary contains. Appendix A starts from the job: Calliope gives
data and tools, the agent writes the story of the move. The working order is four steps — read the
board (`ply`: grade, evaluation, best move, both lines, the FENs, the claims), choose two to four
kinds of remark (§3), check them with the tools, write. Writing distinguishes three kinds of
sentence (review B1):

- **Checked facts** — `sourced`, citing the propositions that hold them.
- **Judgements and assessments** — intent, the game's flow, a lesson, which side is comfortable:
  `interpretation`, citing the nearest evidence, never contradicting it, worded as a reading
  ("~로 보인다").
- **Concrete facts and causes** — "○ attacks △", "△ is lost because of ○", "△ cannot be parried":
  claims of fact, not readings. Checked and written as `sourced`, or left out. Rewording one as a
  reading to pass the check is what the guide forbids.

The check verifies citations, not meaning (`commentary_check_v1`), so the third rule is guidance;
the review trial saw a strong model break it once (§0.3). Two more rules carry the trials' lessons:

- **Lengths are advised, not required** (owner Q2 as the review conditions it). A key moment gets
  4–7 sentences, another move 2–3; a move with little checked gets a short commentary. Trial set 2
  showed that asking to drop unchecked points shortened the commentary; rev. 1 answered with "a
  short commentary is a failure", and the review trial showed the cost of that: what it added was
  loose (§0.3).
- **No general sentences.** An interpretation reaches something on the board — a piece, a square,
  a line. "기회를 놓쳤다", "흐름이 넘어갔다" fit any game. The pre-check's general sentences fell from
  18 of 48 to 5 of 33 with this line.

The rules that hold today (proposition form, a judgement of the subject, notation, reading claims:
ATTRIBUTED, `specific_line`, patterns, INCONCLUSIVE and REFUTED, the agent's own lines) stay, in
one short list. Two lines are new, from the refusals of §0.2: which `use` fits which claim (line
fact by default; `comparison` for a comparison, `result` for a consequence; `line_fact` for a
function or mechanism claim; never the role's name), and that `cites` holds the ids of the agent's
own propositions, not a claim's template.

## 3. The table of remarks

Appendix A's table gives, for each of twelve kinds of remark, the fact to observe (the tool and the
proposition kind), what to check further, the words allowed once it is checked and the words
allowed before (review B2). It names three strengths of evidence and asks the agent to say no more
than the strength it checked:

- **a configuration** — a relation on the board now (`attack`, `pin`, `pattern`): "the queen and the
  rook on d8 are both attacked", never "the double attack cannot be met";
- **a possible line** — what happens along one line (an engine line, an explored line, `material`
  over it): "along the engine line Black loses the bishop";
- **a forced result** — what holds against every reply: only after the replies are checked
  (`legal_moves` for all of them, a judgement of each, or an explored line each).

Where the review found a kind's evidence short of its claim, the table now asks for more:

| Kind | Rev. 1's evidence | Appendix A |
| --- | --- | --- |
| 1. the move's purpose | `attack` after the move | the same relation absent before the move (`facts` at `before`) to say "this move attacks"; without it, "after the move ○ attacks △" |
| 3. a double attack | `pattern(multi_target_attacks)` | a configuration only: "aims at both"; "both cannot be held" after each defence is explored or judged |
| 5. the better move | the best line | `after_reply`, the same reply after both moves (AG-D §4), to say "after the same reply"; the lines alone give "the best line goes on with ○" |
| 7. a forced move | candidates' `engine_score` | "the only move" only when every legal move is checked; otherwise "the candidates shown, ○ and △, all score □ or less" |

Every row names its proposition kinds, and a line under the table says which `facts` family holds
which kind (review N1, and the family errors of §0.3): `attack`, `defence` and `pin` in `pieces`;
`check` and `legal_moves` in `status`; `pattern` in `patterns`; `exposed` in `exchange`; the default
families are `status`, `material` and `pieces`. It says that `explore` without `search` spends no
engine budget. The three examples paraphrase Capablanca's notes to a different game (*Chess
Fundamentals*, game 13; public domain), so no example tells an agent the answer to a game it is
asked about. The sources' kinds that Calliope cannot back (motives and style, openings and history,
questions to the reader, exclamations) are left out.

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
seven trials, and the agents rewrote sentences around it. AG7's move token is

    (?:(\d+)(\.|\.\.\.) ?|(\.\.\.))?SAN

— a number with one or three dots, or three dots alone; one dot without a number matches no move
(review N2: `(\d+)?(\.|\.\.\.)` would take `.d6`). Then, for a move of the cited propositions:

- the side: three dots, with or without a number, require Black to move at the move's position; one
  dot after a number requires White; this is checked whether or not a number is written;
- the number, when written, is the position's fullmove number, as today;
- no number and no dots: as today (a bare pawn push is a square);
- `.d6` is no move and no square: refused as today.

The capture, check and mate marks hold as today (AM2). `token_rule.move`'s statement says so. The
split rule is unchanged (`...` alone, apart from the move, still reads as nothing and the move
after it as a bare SAN).

## 6. Not changed, and why

- **C.** With C the strong model wrote the best commentary of the trials, and the small models wrote
  board relations that were wrong and passed (§0.1). Without it, the guides got the small model to
  fetch the facts it needed (§0.2, §0.3). C stays out; the next design gives the agent the board's facts
  with the ply, after which C is decided again on measurements.
- **Calliope's sentences in the digests.** Removing them changed nothing in trial set 2; they cost
  the agent little and tell it what Calliope already shows. The guide says not to translate them.
- **The instructions and the check guide.** The pre-check and the review trial ran with today's
  instructions and `check_ko_v1`; their rules are the rules Appendix A keeps.

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

Acceptance trial (recorded in the implementation document; review B3): §0.3's setup with AG7's
server — luna, 3 trials each on the Opera Game and the rapid game, today's guide (`main @ cbbd7da`)
against AG7 — and a hand check of six fixed moments (Opera 9...b5, 13.Rxd7, 15.Bxd7+; rapid
20...c6, 26...Re8, 27.Bxf7+) in every trial. Each sentence of a fixed moment is put in one class:
a restated judgement; a narrated line; a reason backed by its citations (a board fact, a line's
material, a comparison after the same reply); a reading; a general sentence. Apart from its class,
each sentence is marked when it is wrong on the board, when its citations do not support what it
says (meaning, not tokens), or when it states a concrete fact, cause or forced result its citations
do not establish. The document lists every fixed moment's sentences by guide so the reviewer can
check the marks. AG7 passes when, over the six moments of all its trials:

1. it has no wrong sentence today's guide does not also have, and no more wrong sentences in all;
2. it has no more unsupported or unestablished sentences than today's guide, and at most one in a
   trial;
3. it has more backed reasons than today's guide (today's had none in §0.3);
4. every fixed moment it comments has a sentence that is neither a restated judgement nor a
   general sentence;
5. its refusals a trial are no more than today's, and no `facts` call fails on a family name.

Length and the share of general interpretation sentences are reported beside them, not passed or
failed: a longer commentary is not a better one.

## 8. Next

The board's facts with the ply — the pins, double attacks, sole defenders and loose pieces of the
positions before and after the move, and the same reply after the best move and the played one — as
citable items in the digest (the "why" the trials never reached, §0.3). After it: C measured again,
and whether a submission of a key moment must cite a board fact.

Beyond that (owner, 2026-10-17): the commentary's path end to end — what the agent is given, in what
shape, and what it is asked — so that the model understands what a remark means and what its
evidence proves, and acts as intended, rather than being told after the fact what not to write.
The trials show the limit of guidance alone: agents take the shortest path that passes the check.

## 9. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Keep `commentary_ko_v1.md` in the repository, unserved (H1)? | Yes: older commentaries name its digest. The review approves. |
| Q2 | The lengths (4–7 sentences for a key moment, 2–3 otherwise; 12 is the check's maximum)? | Advised, not required, as the review conditions its approval (§2). |

## 10. Review dispositions — rev. 1 (`968e62c`), independent review: NOT_READY

| # | Finding | Disposition |
| --- | --- | --- |
| B1 | The guide kept unchecked readings unconditionally; the check does not verify meaning, so a cause or a refutation reworded as a reading would pass | §2: three kinds of sentence; readings never contradict their evidence; concrete facts, causes and forced results are checked and sourced or left out. Tried first (§0.3). |
| B2 | Some kinds' evidence does not prove the claim: an `attack` after the move is not the move's doing; `multi_target_attacks` is a configuration; a few scores do not make a move the only one; `after_reply` unused | §3: observable fact → further check → words allowed after and before; three strengths of evidence; kinds 1, 3, 5, 7 as the review asks. |
| B3 | The acceptance measured length, not quality, and allowed today's errors repeated | §7: six fixed moments hand-checked by sentence class, with wrong, unsupported and unestablished sentences counted; length reported only. |
| N1 | `facts` families not named (`patterns`, `exchange`) | §3 and Appendix A: which family holds which kind; the default families. |
| N2 | The regex `(\d+)?(\.|\.\.\.) ?` admits `.d6`; the side check should not depend on the number | §5: three dots alone in the pattern, one dot only after a number; the side checked with or without a number. |
| note | §0 counts 77 trials, not 78 | The 78th was the run that checked the scratch server's switches, now counted in trial set 2 (§0); with the review trial, 85. |
| Q1, Q2 | Q1 approved; Q2 approved on condition the lengths are not a minimum | §9; §2. |

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
4. **씁니다.** 문장은 세 가지입니다.
   - **확인한 사실**(sourced): 명제로 확인한 것. 그 명제를 인용합니다.
   - **판단과 평가**(interpretation): 의도, 흐름, 교훈, 어느 쪽이 편한가. 인용한 근거와 **모순되지 않아야** 하고, 단정 대신 "~로 보인다"처럼 씁니다.
   - **구체적 사실·인과**("○가 △를 공격한다", "○ 때문에 △를 잃는다", "△를 막을 수 없다")는 해석이 아니라 사실 주장입니다. 해석 문장으로 바꿔 쓰지 마세요. 도구로 확인해 sourced로 쓰거나, 확인하지 못하면 쓰지 않습니다.

분량은 권장입니다: 핵심 장면 4~7문장, 덜 중요한 수 2~3문장. 등급을 말하는 문장은 하나면 충분하고, 나머지는 "왜"와 "어떻게"에 씁니다. 확인한 말이 적으면 짧게 쓰세요. 분량을 일반론으로 채우지 마세요.

해석 문장은 판의 구체적인 것(기물, 칸, 수순)에 닿아야 합니다. "기회를 놓쳤다", "흐름이 넘어갔다", "타이밍이 중요했다"처럼 어느 대국에나 맞는 일반론만 있는 문장은 쓰지 마세요.

## 해설가가 하는 말: 상황별 주장과 근거

위치는 `{{"ply": n, "at": "before" | "after"}}`(그 수를 두기 전/후)입니다. 근거는 세 가지 세기가 있습니다. **배치**(지금 판에 있는 관계), **가능한 수순**(한 라인에서 일어나는 일), **강제된 결과**(상대의 모든 응수에서 성립). 확인한 세기만큼만 말하세요.

| 유형 | 관측할 사실 (도구 → 명제) | 더 확인할 것 | 확인하면 쓸 수 있는 말 | 확인 전에 쓸 수 있는 말 |
|---|---|---|---|---|
| 1. 수의 목적 | `facts(수 뒤)` → `attack`·`check`·`pin` | `facts(수 전)`에 같은 관계가 없음 | "이 수로 ○를 공격하게 됐다" | "수 뒤 ○가 △를 공격하고 있다" |
| 2. 다목적 | `facts` 두 관계 | 막힌 수를 `explore`로 두어 `material` 손실 | "○하면서 △를 막는다" | "○와 △에 닿는다" |
| 3. 이중 공격 | `facts(families: ["patterns"])` → `pattern`(multi_target_attacks) | 상대의 방어 후보마다 `explore`/`judge_move`로 하나를 잃음 | "두 곳을 함께 막을 수 없다" | "○와 △를 동시에 노린다"(배치) |
| 4. 실수의 반박 | 둔 수의 라인 → `engine_line`, 그 라인의 `material` | — | "엔진 수순 ○에서 △를 잃는다"(그 라인에서) | — |
| 5. 더 나은 수와 비교 | 두 라인 → `engine_line` | 같은 응수 r 뒤 두 국면을 `after_reply`로 비교 | "○였다면 같은 응수 △ 뒤 □" | "최선수 라인은 ○로 이어진다" |
| 6. 왜 자연스러운 수가 아닌가 | `judge_move(수 전, ○)` → `judgement` | `explore([○, △])` → `material` | "○는 △ 때문에 안 된다(그 수순에서 □)" | "○는 평가가 □로 낮다" |
| 7. 강제·유일한 수 | 후보들의 `engine_score` | `legal_moves`로 모든 수를 보거나 각 후보를 판정 | "유일한 수다"(모든 수를 확인했을 때만) | "보인 후보 ○, △는 모두 □ 이하였다" |
| 8. 국면 평가 | `facts` → `pin`, `defence`, `pattern`(sole_defenders, families: ["patterns"]), `exposed`(families: ["exchange"]) | — | 관계 그대로("d7 나이트가 핀에 걸려 있다") | "약하다", "답답하다"는 해석 |
| 9. 계획 | `explore`로 계획 수순, 끝 국면의 `facts` | 상대 응수를 넣은 수순 | "○를 거쳐 △를 노릴 수 있다"(가능한 수순) | 의도는 해석 |
| 10. 판단의 차이 | 두 수의 `judge_move`/점수 | 막지 못한 △를 `explore` | "△를 막는 쪽의 평가가 더 좋았다" | 둔 사람의 의도는 해석 |
| 11. 흐름 | 앞뒤 장면의 판정과 평가(이미 인용한 명제) | — | — | 해석(근거와 모순 없이) |
| 12. 원칙·교훈 | `facts`(전개되지 않은 기물, 캐슬링 전 킹) | — | 국면 사실 | 교훈은 해석 |

예시(다른 대국의 해설 방식):
- 판단의 차이(10): "백은 나이트의 핀을 유지하려고 비숍을 물렸지만, 흑의 캐슬링을 막는 것이 더 중요했다. 다른 대각선으로 갔다면 그것을 막을 수 있었다." → 두 비숍 후퇴의 판정 비교 + 캐슬링이 가능한지 국면 사실.
- 다목적(2): "나이트가 물러나 비숍의 대각선을 열고, 동시에 백의 e폰 전진을 막는다. 전진하면 나이트가 비숍을 잡고 폰을 얻는다." → 대각선의 `attack` + 폰 전진 수순의 `explore`와 `material`.
- 왜 자연스러운 수가 아닌가(6): "나이트를 e7로 보내는 수는 안 된다. Nd5가 있기 때문이다." → `explore(moves: [Ne7, Nd5])`.

표의 `attack`, `defence`, `pin`, `check`, `legal_moves`, `pattern`, `exposed`는 **명제 종류**이고 `facts`의 family가 아닙니다. 그 사실이 있는 family는 이렇습니다: 공격·방어·핀은 `pieces`, 체크·둘 수 있는 수는 `status`, 패턴은 `patterns`, 노출은 `exchange`. `facts`의 기본 family는 `status`, `material`, `pieces`입니다.

나쁜 해설은 유형 4·5만 씁니다("실수다. ○가 더 나았다"). 핵심 장면에서는 유형 1·3·6·8 중 하나를 확인해 넣으세요. `explore`는 `search` 없이 두면 엔진 예산을 쓰지 않습니다.

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
