# RX4a evaluator notes: arm A-min → candidates_min_v1

Inputs read: `commentaries.md`, `judging.json`, `references/*.json` (Train), `runs/*/agent.jsonl`, `guide_commentary_min_v1.md`, `tool_definitions.py`.
Probes: `probe.py` in WSL. The raw output is in `out/scratch/probes/` and summaries are in `out/scratch/probe_summary*.txt`.
Nothing outside this directory was opened, and no model API was called.

## The main finding: the agent does not investigate

Across all 12 A-min runs the agent never called `explore`, `facts` or `judge_move`. It called `detail` once (hung, run M8JCYW).
Each run does the same thing: `analyze_game` → `game_overview` → `ply` for every overview moment (10–16 plies) → `submit_commentary` in batches.
The user prompt asks for the whole game, so the effort is spread over all the moments, and each commentary is written from the `ply` digest alone.
Every decisive cause except fourth 56 was in the digest (`route: in_digest`). The failures are therefore about **which digest items were used and whether their outcome was stated**, not about missing data.
So every lesson ties a condition visible in the digest, quoted in the digest's own words, to one concrete tool call with its arguments.

## Per moment (Train)

- **fourth 37 (19.Nh6+, mistake), 3× partly, score 3.** All runs cited the weakness (knight capturable, "3 points") and the lost defence. They did **not** cite the scene item: the queen was attacked by a pawn before the move and is still attacked after. They also did not say that the played line takes the knight back (Qxd7), so the line's material is unchanged. Two runs called the best line "better in material" without what or why. One ✗ (56BPH0): it invented that the best move "retreats the knight". Cause: no exploration of the played line, and the scene was ignored. → L02, L03.
- **fourth 38 (19...Kh8, mistake), 3× partly.** The runs said the best capture was better (eval −4.21) and that the d7 knight stays attacked. None said that **both lines are the same knight swap with equal material** and only the order differs. The only comparison claim is in expected score, with no material claim. Cause: the grade is not explained by line material, and the agent did not play either line (RX2 pattern 1). → L05.
- **fourth 56 (28...Bxg3, best/brilliant), cause 1 partly ×3.** The decisive cause is on_request: if White takes the offered bishop, there is mate in 2. The runs cited `capture_holds` ("expected score 100%") without the reason. One ✗ (MRRPJF) confused the d5 and d6 bishops. Cause: the agent never played the capture of the offered piece (RX2 pattern 2). → L01.
- **fresh 56 (28...Qe6, mistake): 1 explained, 2 partly.** The explained run (ZJQBFG) stated "best line +1 point vs played line no change" with the comparison claim. The partly runs said only "also good for Black in material", or muddled the square count. Cause: the number and the capture were not made concrete. → L06.
- **fresh 62 (31...Qf6, inaccuracy), 3× partly.** The runs mentioned that the bishop was still attacked by the pawn. None said it is **taken** and that the line ends a net point down, nor that the best move removes the attacking pawn. One ✗ (ZJQBFG) misread the "since move N" note on a lost defence as the time the defence began. → L03, L04.
- **fresh 76 (38...Rxh5, mistake), 3× explained, score 4.** The decisive cause was fine. The ? sentences recap earlier moments (28...Qe6, 31...Qf6) or the actual continuation. No lesson (see the open issue below).
- **hung 14 (7...Bxe2, blunder), cause 1 partly ×3; cause 2 partly in 60WN4H.** All runs said the queen was left attacked. None played the played line: an in-between check, then the pawn takes the queen and the queen is taken back. Material comes out equal, yet the eval is +3.88. 60WN4H also gave the best move only as an evaluation, not its pawn capture (+1). → L02, L06 (and L03 is consistent).
- **hung 25 (13.Rb1, mistake): 1× 5, 2× partly.** The partly runs said the pawn "remains attacked" but not that it is taken (1 point). → L04.
- **hung 68 (34...Qb3, blunder), explained ×3.** The ? sentences are the actual continuation (35...bxa3 36.Rxa3), the eval after 35.Rxb3, and earlier history. The runs did read ply 69–71, but the judge's reference does not show them. No lesson.
- **rapid 40**: out of scope (positional reason). Not used.
- **rapid 52 (blunder), explained.** One ✗ (WP0519): "mate on the next move" for an M4. This is a wording slip with no tool cure, so there is no lesson.
- **rapid 54 (mistake), explained.** The ? sentences are the actual continuation and the game result, which the guide's "summarise the final scene" asks for. No lesson.

**Open issue, not a lesson:** about 12 ? sentences come from the guide's instruction to open the first scene with the opening and close the last scene with how the game was decided. The judges' reference holds only this moment, so these sentences are graded unsupported (hung 68 scored 4 vs 5). No tool call cures this, so I left it to the guide and the judging, not a lesson.

## Candidates

Each lesson's condition quotes the digest's own wording so the agent can match it literally. Each action is one call with its arguments spelled out.

- **L01: offered piece → explore the capture with search.** Condition: claims with "내준다 … 상대는 …로 잡을 수 있다" or "내준 기물을 상대가 잡아도". Checked: `explore fourth {ply:56,at:after} [the capture]` with search returns mate −2 (Rxf2+ Rxf2 Qxf2#), the decisive cause exactly. It should turn three partly verdicts into explained, and the "distinguish by square" clause targets the bishop mix-up ✗.
- **L02: "played line no material change" but a piece is capturable → explore the played pv for 6 moves.** Checked: fourth 37 gives material 0, −3, 0, 0 (the knight is retaken). hung 14 needs 6 moves: after 5 the balance is −3 and the 6th move retakes. That is why the lesson says 6. The success line forces "who takes what, what is taken back, material equal, eval falls", which is the decisive cause in both games.
- **L03: own piece left attacked (scene "계속 받는다" / held) → judge_move the best move and read its scene.** Checked: fourth 37's best move answers "queen moved, no longer attacked" plus a `rescue_v1` claim (9 points). fresh 62's best move answers "captured the attacking pawn" for both targets. hung 14's best move answers "queen no longer attacked". hung 25 is excluded: its best move's answer does not show the pawn defended. This gives the agent a citable contrast (left it vs best saved it), which the fourth 37 runs lacked entirely.
- **L04: the opponent's first move in the played line captures a weakness/held piece → explore that capture with search.** Checked: hung 25 gives material −1 and end search −3.99. fresh 62 gives +3 and end search +3.14. There Black regains part, so the lesson sends the net to the claim's value (1 point). This targets "attacked" being written without "taken".
- **L05: only an expected-score comparison, with mutual captures in both lines → explore both lines 3 moves each.** Checked on fourth 38: played 0, +3, 0 (end −1.35) vs best −3, 0, 0 (end −3.99). Material is equal, and the difference is the order and the eval, which is the decisive cause.
- **L06: "best line gains N points" → explore the best line for 3 moves and find the capture.** Checked: fresh 56's best line shows −1 on its first move while the played line stays 0 throughout. hung 14's best move answers with a `material_gain` claim (pawn, +1). This targets the vague "better in material" sentences of the partly runs.

Expected uptake: most lessons fire on a literal phrase the agent already sees in `ply` (e.g. "물질 변화 없음", "내준 기물을 상대가 잡아도", "계속 받는다", "held"). Each action is one call with fixed arguments: position `{ply, at}` plus the moves from `lines`. That is the kind of action the screening showed the agent will actually take.
The risk is the whole-game workload: the agent may still skip tool calls under budget. Even so, L01 and L03 each need only one call per moment.
