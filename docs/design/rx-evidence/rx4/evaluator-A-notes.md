# RX4a evaluator notes: arm A, Train, candidates_v1

## What all twelve runs share

None of arm A's 12 Train runs called `explore`, `facts`, `judge_move` or `detail`. Each run called
`open_game`, `analyze_game`, `game_overview`, `ply` on every moment, a couple of `definitions`, then
`submit_commentary` and `show_game`. The only `x` handles cited are the server's own `same_reply` lines.
So every "partly" below is a cause the `ply` digest did not spell out, which the agent never went and got.
Each lesson below names the tool call that gets it.

## Per moment

**fourth 37 · 19.Nh6+ (mistake): partly ×3 (scores 4, 3, 3).** The decisive cause has two halves. (a) The
played line is a knight-for-knight trade, so material is unchanged. (b) The best move moves the queen off
the pawn's attack, and the comparison claim gives it +1 material. All three runs said the knight on h6 is
attacked and gave the evaluations. None said (a): T9HBD4 even wrote that White "loses the knight's
value". Only NNF2EB said the queen was attacked (it cited the scene), and none said the best move rescues
it. ZBPK7P cited `better_move_v1` but wrote only the two scores. Cause: no `judge_move` on the best move, and
the comparison claim's material halves were not written. → L01, L02, L04.

**fourth 38 · 19...Kh8 (mistake): explained ×1, partly ×2.** Both lines trade knights; the engine prefers
taking at once by 14 pp. NNF2EB wrote that in the played line White takes d7 and Black takes h6 (both
captures) and got explained. T9HBD4 said only that d7 "can be taken" (the square count, a loss) and
ZBPK7P never closed the trade. Cause: the played line was not played out to its recapture. → L04.

**fourth 56 · 28...Bxg3 (best, brilliant): partly ×3 on both causes (3, 3, 2).** The decisive cause is
`on_request`: if White takes the offered bishop, mate in 2. All three wrote "expected score 100%" from
`capture_holds_v1`, and none played the capture. ZBPK7P also got sentence 1 ✗: it said the offered d5
bishop made the capture, when it was the d6 bishop. Cause: no `explore` of the capture after the move, which
is RX2 pattern (2), confirmed. → L03; the ✗ → L07.

**fresh 56 · 28...Qe6 (mistake): explained ×1, partly ×2.** AJHE4A wrote both halves of
`better_move_v1`: played line, no material change; best line, +1. PVZ87E never cited it, and 6PV6G9 cited
it but wrote only "the latter is a line that gains material". → L02.

**fresh 62 · 31...Qf6 (inaccuracy): explained ×1, partly ×2.** The bishop left `held` is lost; the played
line ends one point down; the best move takes the attacking pawn first, and its line has no material
change. AJHE4A wrote both halves of the comparison. PVZ87E and 6PV6G9 gave lines and scores only, and
nobody said that the best move removes the attacker. → L02, L01.

**fresh 76 · 38...Rxh5 (mistake): explained ×3.** No cause failure. AJHE4A and PVZ87E each have a `?`
sentence calling earlier moments "the decisive flow": the reference does not grade those moves. That is
not a strategy gap a tool fixes, so it gets no lesson.

**hung 14 · 7...Bxe2 (blunder).** Cause 1, a zwischenzug that wins the queen while Black wins White's
queen back, so material is equal: explained ×1 (ZTDKE1 wrote both queen captures), partly ×2 (V3DGJG and
08BPB3 wrote only that White takes the queen). Cause 2, the best move escapes and wins a pawn: partly ×3.
ZTDKE1 cited `better_move_v1` but wrote "a better material result". Cause: the played line was not played to
its last recapture, and there was no `judge_move` on the best move. → L04, L01, L02.

**hung 25 · 13.Rb1 (mistake).** Cause 1, the `held` pawn: ZTDKE1 partly (it never cited the held item),
the other two explained. Cause 2, the best move defends the pawn so a capture is recaptured: partly ×2.
ZTDKE1 wrote "a comparison that there is no gain", and V3DGJG wrote "a choice of 15.dxc5". 08BPB3 tied the
same_reply to the c-pawn's defence and got explained. → L05, L06.

**hung 68 · 34...Qb3 (blunder): explained ×3.** V3DGJG has sentence 2 ✗ `old_attack_as_new`: it says the
queen "became capturable at the same time", although the `held` item says it was capturable before the
move. It also has two `?` sentences about the actual game continuation, which the reference lacks. → L06 for
the ✗.

**rapid 40 · 20...c6:** outside the target (positional reason), so it is not counted.

**rapid 52 · 26...Re8 (blunder).** Cause 1 explained ×3. Cause 2 is partly ×3: in the best line Black
also loses one point, but without mate. Every run gave only "+4.32"; YM6E6W cited `better_move_v1`
("mate vs 1 point lost") without writing it. → L02.

**rapid 54 · 27...Nxf7: explained ×3.** The only issues are `?` sentences about the game actually
ending on 28.Rxe8#, which the reference lacks. No lesson.

RX2's pattern (1), the game's own continuation: in Train the moments whose grade the line's material does
not explain (fourth 38, hung 14 cause 1) failed because the *engine's played line* was not played to its
recapture, not because of the game's later moves. In fourth 38 the game itself leaves the engine line at
move 20. So I wrote L04 on the played engine line instead.

## Candidates: what I checked with probe.py and why I expect each to help

- **L01, `judge_move` the best move when the scene or a `held` item shows an attacked piece.** fourth
  `judge_move {"ply":36} g4h3` gives a scene item ("…h3로 옮겨 … 공격을 더는 받지 않는다") and
  `rescue_v1` SUPPORTED. hung `judge_move {"ply":13} e5c5` gives the same kind of scene plus
  `material_gain_v3` (8...Qxc4 wins the pawn), which is hung 14's cause 2 verbatim. fresh
  `judge_move {"ply":61} f5e4` gives scene items "공격하던 백 폰(e4)을 잡았다" for both the bishop and
  the pawn. These are the missing halves in 8 partly moment-runs. The weak spot is hung 25: `judge_move` on
  13.d4 shows only a `lost_defence`, which is why L05 exists.
- **L02, state both halves of the material comparison, located with `explore`.** In fresh, `explore
  {"ply":55}` on the best line shows balance -1 at its first move, while the played line stays 0. In
  rapid, `explore {"ply":51}` on the best line shows +1 at its 8th ply (30.Rxf7). fourth 37's best line
  and fresh 62's played line stay 0 through 8 plies: the gain or loss comes later. The fallback therefore
  tells the agent to write the claim's two results without naming a move. The runs judged explained wrote
  exactly these halves.
- **L03, `explore` the offered capture after the move with search.** fourth `explore {"ply":56,"at":"after"}
  ["d7d5"]` gives an end search whose rank 1 is Rxf2+ Rxf2 Qxf2#, mate -2. That is the owner's
  decisive cause, missing from all three runs.
- **L04, play the played line to its last recapture.** hung `explore {"ply":13}` on five plies gives
  balance -3, -3, -3, +6, -3: it only evens out after the next recapture, so the lesson says "to the last
  recapture". fourth `explore {"ply":37}` [Kh8, Qxd7, Qxh6] gives 0, +3, 0: material is equal, as the
  key cause says.
- **L05, `explore` [best, the capture, the recapture] for a `held` piece the best move protects.** hung
  `explore {"ply":24}` [d3d4, f8c5, d4c5] gives 0, -1, +2: the capture is recaptured, and Black ends two
  points down.
- **L06, `facts` before the move for a `held` piece, so it is never called "newly" capturable.** hung
  `facts {"ply":67} ["exchange"]` shows the black queen exposed before the move (gain 4, first capture from
  the rook). It answers one ✗ and one missed held item. The evidence is small.
- **L07, `facts` pieces to tell two same-type pieces apart.** fourth `facts {"ply":55} ["pieces"]` lists
  the attackers by square. It rests on a single ✗ and is the weakest candidate; drop it first if screening
  is tight.

I could not check `detail` with probe.py: each probe call opens its own session, and a handle from an
earlier call is "not served in this session". So no lesson relies on `detail`.

Order of expected value: L01 ≈ L02 > L03 > L04 > L05 > L06 > L07.
