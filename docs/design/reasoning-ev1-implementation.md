# Reasoning — packet EV1 implementation: explanation v2, part 1

Status: **rev. 1 — awaiting independent implementation review**.
Date: 2026-10-14. Design: [`reasoning-explanation-v2-design.md`](reasoning-explanation-v2-design.md)
rev. 4 (EV-D, three reviews NOT_READY applied, re-review READY, #89). Base: `main @ 5c08856`.

## 1. Scope delivered (EV-D §5)

| Place | Change |
| --- | --- |
| `reasoning/lines.py` | `checking_draw(view, line, side)`: the `ChecksDrawFinding`, `None`, or `NOT_COMPUTED(move \| draw \| wdl)`; `checking_draw_evidence`; `CHECK_RUN = 2`, `DRAW_CP = 10`, `DRAW_WDL = 900` (EV-D §2.1) |
| `reasoning/findings.py` | `DrawKind`, `ChecksDrawFinding`, `ReplyKind`, `ReplyFinding` (with `played_gain`, `best_gain`, rev. 4); all in `KINDS` |
| `reasoning/catalogue/draws.py` (new) | `ChecksDraw` (`checks_draw_v1`, CONSEQUENCE), `ChecksDrawMissed` (`checks_draw_missed_v1`, COMPARISON) |
| `reasoning/catalogue/comparison.py` | `BestStopsReply` (`best_stops_reply_v1`): RESCUES, DEFENDS (the same reply at `R` and `C`, `g(R) ≥ 1`, `g(C) ≤ 0`, the new defender's recapture), COVERS; per-kind needs; the node `C` without a search |
| `reasoning/catalogue/__init__.py` | `CATALOGUE_V1`: `checks_draw_v1` after `material_gain_v2`; `checks_draw_missed_v1`, `best_stops_reply_v1` after `better_move_v1` (29 templates) |
| `reasoning/planner.py` | `ExplanationPlan.detail`; `DRAWS` (rule 3, after material); `COMPARISONS` with `checks_draw_missed_v1` after `better_move_v1`; rule 6b with `DETAILS`, `DETAIL_AFTER` |
| `reasoning/render/__init__.py` | `fmt_square`, `fmt_side`; `bind` for the three templates; S6b; G4 for the detail; G5 refined (§2 note 2) |
| `reasoning/render/phrases/en.toml` | `[checks_draw_v1]`, `[checks_draw_missed_v1]`, `[best_stops_reply_v1]`, their `[claim]` names |
| `results/document.py` | `_ref` for kind `square`: `{"kind": "square", "square", "fen"}` (the schema and the viewer already accepted it) |
| `docs/design` | R2-D §15, R3-D §19, R4-D §11 and EV-D §11 record the amendments |

`labels.py`, `build.py`, `encoding.py` and the fact engine are unchanged: MISS keeps its ground,
and the build digest changes through the template list, the type registry (the new findings and
the plan field) and the phrasebook digest.

## 2. Implementation notes

1. **The reply claim's target is `Lp`'s segment** (EV-D §11). EV-D §3.1 put the target on
   `seg(L1)` and §3.4 (rev. 3, N3) made the scope's plies `Lp`'s window. R0-D §9.2
   (`check_scope`) refuses a scope with more plies than its target's segment, so with that target
   33.b6 (COVERS) and 50.Bc5 (RESCUES), both expected in EV-D §6, raised that error: their `L1`
   PVs are attached over fewer plies than `Lp`'s window. The target is now `line_target(seg(Lp))`,
   which always holds the window; the context stays `LineContext(seg(L1))`; the scope still names
   rank 1 among its searches, as `better_move_v1` names `Lp`. The qualification text is the same
   ("the engine line at depth 12").
2. **A detail sentence opens with the best move** (R3-D §19). EV-D §3.4's sentences begin with
   `{best}`; R3-D's G5 refused any `sentence` form beginning with a slot (a slot's first letter
   could need a capital). The rule now admits a first slot whose value is a numbered move
   (`TraceRef` kind `move` or `search_move`, text starting with a digit); any other slot at the
   start is still refused (test `test_a_sentence_may_open_only_with_a_numbered_move`).
3. **The kind is read before any `exchange` request** (EV-D §3.2, N4): `r`'s capture and `b`'s
   piece decide the kind; each kind checks its rule facts (`move`, `squares`, `status`, identity,
   `Lp`'s outcome) and only then asks for `exchange` at its own nodes: RESCUES `P`, `A1`; DEFENDS
   `R` and the extension of `B1` in one round, then `C`; COVERS the extension, then `C`. When `C`
   already exists (the best line plays `r` itself), DEFENDS asks for `R` and `C` in one round.
4. **DEFENDS checks** (rev. 4, B7): an ordinary capture (no en passant, no promotion, not the
   king); the same victim `V` on `s` at P, `A1`, `B1`; `r` legal at `B1`; the piece `b` moves is an
   unpinned attacker of `s` at `B1` and not among `m`'s attackers at `A1` (pinned ones included);
   `Lp` loses material from ply 2; at `C` the move is the same capture (victim, capturer, square)
   and `X` stands on `s` at `R` and `C`; `g(N) = v − ex(N, s).gain` with `g(R) ≥ 1`, `g(C) ≤ 0`;
   `ex(C, s).first_capture` starts on `b`'s to-square. `ex(A1, s)` and `ex(B1, s)` are never read.
5. **`checks_draw_v1` tries the opponent's run first**; a side whose run is a checking draw in `L1`
   too is skipped, and a missing record (`draw`, `wdl`) of either side is reported when no side is
   `SUPPORTED`. The mover / opponent phrase is read from the segment's first ply (the mover plays
   the odd plies from P), so the renderer reads nothing outside the claim's references.
6. **An equivalent condition.** A checking run excludes a mating check, and the window must not
   end in checkmate (EV-D §2.1, conditions 1 and 3). A mate ends the line, so the mating check is
   always the window's last ply and either condition alone excludes it; the mutation that drops
   the first is not caught by a test (§3.1).

## 3. Evidence

### 3.1 Tests (EV-D §7)

| Obligation | Test |
| --- | --- |
| 1 the checking draw | `tests/reasoning/test_explanation_v2.py`: runs of 1 / 2 / 3 checks; a quiet ply breaking the run; a checking mate ending it; scores 0, ±10, ±11 and a mate score; WDL draw 899 / 900 / unavailable (the score curve grades); THREEFOLD and FIVEFOLD with and without the WDL; a third occurrence "can be claimed", a fifth "is drawn"; `HISTORY_UNKNOWN` (thirty unknown plies) is REPEATED by the WDL, not THREEFOLD; a repetition at `N_{q−1}` only is SCORED (N1); a repetition of the game's history and one inside the window; a Black checker and a White one; a missing `draw` record (wrapped view) |
| 2 `checks_draw_v1` | the opponent's checks after a blunder (the whole text; evidence paths resolve; the scope reads both lines and `Lp`'s six plies); the mover's own checks ("It settles for checks"); the same side's checks in `L1` (REFUTED); a move with no loss (not proposed); no WDL (INCONCLUSIVE `NOT_COMPUTED(wdl)`, not rendered) |
| 3 `checks_draw_missed_v1` | the 38...f5 shape: THREEFOLD, chosen over `missed_gain_v1`, one "Instead", the whole text; `Lp` also a checking draw (REFUTED); the best line drawn without checks (REFUTED); a MISS ply keeps `missed_gain_v1` as its comparison |
| 4 `best_stops_reply_v1` | COVERS: SUPPORTED with its finding, evidence and the node `C` without a search, needs (the extension, then `C`; none at P, `A1`, `R`, `B1`); `covers.material` (net 4); REFUTED for `r` illegal after `b`, no SEE gain, the first capture by another piece, a square covered at `A1` (by a knight, and by a queen while `b`'s rook would take first), a reply that does nothing later. RESCUES: SUPPORTED, needs at P and `A1`; REFUTED for `b` not in `safe_moves` and for a piece not exposed at P. DEFENDS: SUPPORTED with `g(R) = 1`, `g(C) = 0`, the recapture `c3e4`, needs (`R` and the extension, then `C`; never `A1` or `B1`); `C` already in `L1` (one round); a reply that is not the least valuable attacker (the queen takes: `g(C) = −5`, SUPPORTED, while the square's exchange at `B1` still wins for Black); a square-level exchange of 0 with the reply still winning (REFUTED); another capturer at `C`, a pinned defender, a defender already attacking at `A1` (pinned), a checking best move (`1.Nf6+`), a king capture, en passant, a promotion (all REFUTED). `max_rounds = 1` (ROUND_LIMIT), `max_ensure_nodes = 0` and no node room (BUDGET): INCONCLUSIVE and not rendered |
| 5 plan and guard | the detail after `better_move_v1`, `missed_gain_v1`, `better_alternative_v1` and the MISS sentence; none after `mate_missed_v1` or `checks_draw_missed_v1`; G4 refuses no comparison, two details, another template, an unsupported detail, a detail after `checks_draw_missed_v1`; G5 refuses a sentence opening with any other slot; the plan digest covers `detail`; every earlier corpus text is unchanged |
| 6 through the renderer | four corpus cases (`checks_draw`, `checks_draw_missed`, `reply_covers`, `reply_defends`; 18 in all) run `explain`, `trace` = `render`, save / load and the result document like every case; `trace`, save and reload for each kind; the stored tree keeps `C`; `tests/results/test_result.py`: COVERS names the square on `B1`'s board, the reply played from `B1`, the queen and `2.Qxe2` on `C`'s; DEFENDS the pawn and the square on `B1`, `1...dxe4` from `A1`, `2.Nxe4` from `C`; the draw segments name their lines; `tests/viewer/test_viewer.py` draws them (the ring on e2 with the arrow a4→c2, then b5→e2, then c2→e2; the four DEFENDS frames; the five checks); EA1's coverage test reaches all 29 templates |
| 8 build identity | a graph made without the three templates is refused by `load` ("re-analyse"); the shipped build names them |

**Mutations**, each run against `test_explanation_v2.py`: the score bound made exclusive (2
failures), the WDL bound exclusive (1), the repetition counted from `N_{q−1}` (2),
`HISTORY_UNKNOWN` read as true (1), DEFENDS with `g(C) ≤ 1` (1), DEFENDS without the legality
check (1), DEFENDS without the new-defender check (1), COVERS with the first capture by any piece
(1), COVERS without the covered-square check (1), RESCUES without `safe_moves` (1), rule 6b after
any comparison (2), G4 admitting two details (1). A mating check kept in the run is not caught: an
equivalent mutant (§2 note 6).

### 3.2 The owner's two games (EV-D §6, §7.7)

Both games re-run with `tools/explain_game --json` (Stockfish 19, `d12_mpv5_v1`) and compared,
sentence by sentence, with EA1's documents (build `52dcd83d…` → `919adc9d…`). Every ply's grade, loss
and best move is the same as before, so every change below is the new rules.

**836/829** (78 plies): 2 plies changed.

| Ply | Grade (loss) | Removed | Added |
| --- | --- | --- | --- |
| 33.b6 | blunder (447) | — | "Along the engine line, Black then gives check after check, 35...Qxe1+ 36.Kg2 Qe2+ 37.Kg1, and the engine scores it as a draw." and, after the MISS sentence, "33.Qc2 covers e2: after 33.Qc2, 33...Qe2 would lose the queen on e2 in the exchange there, starting with 34.Qxe2."; the scope adds the engine line and static exchange evaluation |
| 38...f5 | blunder (530) | "Instead, 38...Qe2+ was stronger." | "Instead, 38...Qe2+ was needed: it starts a series of checks, 38...Qe2+ 39.Kg1 Qe1+ 40.Kg2 Qe2+, repeating the position a third time, so a draw can be claimed."; the scope is the engine line |

**829/808** (`g1012`, 101 plies): 4 plies changed.

| Ply | Grade (loss) | Added |
| --- | --- | --- |
| 14...O-O | inaccuracy (105) | "14...Be6 defends the pawn on d5: if 15.cxd5, the static exchange on d5 yields no net gain, starting with 15...Bxd5." |
| 49.Bxa3 | inaccuracy (126) | "49.Ng5+ saves the knight on e6 from 49...Kxe6." |
| 50.Bc5 | inaccuracy (117) | "50.Nc5 saves the knight on e6 from 50...Kxe6." |
| 51.a4 | inaccuracy (114) | "51.Nc7 saves the knight on e6 from 51...Kxe6." |

Each of these adds "piece exchanges judged by static exchange evaluation" to its scope sentence.
These are exactly the changes EV-D §6 expected.

One run made while the test suite loaded the machine showed 4...Nf6 "could not be judged (the
engine search was incomplete)" and a changed 5.d4; both plies, re-run alone, are EA1's text
unchanged (a search stopped by its deadline under load, not a rule of this packet).

Every other ply's text is unchanged.

**The DEFENDS measurement** (EV-D §6, rev. 4): at 14...O-O, `r` = 15.cxd5 takes the pawn on d5;
`g(R) = 1` (after 14...O-O 15.cxd5 Black wins nothing back on d5) and `g(C) = 0` (after
14...Be6 15.cxd5 the exchange gives the pawn back), the first recapture 15...Bxd5 (`e6d5`) from
14...Be6's square. DEFENDS holds and is rendered.

**The §0 scan, re-run with the shipped code** (every ply of both games, 179):

| Template | SUPPORTED | REFUTED | INCONCLUSIVE |
| --- | --- | --- | --- |
| `checks_draw_v1` | 1 (33.b6, SCORED) | 32 | 0 |
| `checks_draw_missed_v1` | 1 (38...f5, THREEFOLD) | 32 | 0 |
| `best_stops_reply_v1` | 5: COVERS 33.b6; DEFENDS 14...O-O; RESCUES 49.Bxa3, 50.Bc5, 51.a4 | 28 | 0 |

The five reply plies of EV-D §0.3 all survive the rev. 4 rule, and no other ply is supported.
Over every standard line, both sides, 21 lines are checking draws: 1 THREEFOLD (38...f5's `L1`),
11 REPEATED, 9 SCORED. EV-D §0.2 counted 24 because its scan read each line's whole PV; the
shipped rule reads the material window, inside which three of those runs do not end the window
(27...Qd8's `Lp` and `L1`, 34.Bf2's `L1`), none of them on a ply graded INACCURACY or worse (EV-D
§11).

### 3.3 Test runs

- `tests/reasoning/test_explanation_v2.py`: 61 passed.
- `tests/reasoning`, `tests/results`, `tests/viewer`, `tests/test_package_boundaries.py` (the
  Stockfish tests excluded): all passed.
- The whole suite (`pytest -q tests`, 17 minutes, while the two games ran beside it): 1066 passed,
  27 skipped, 2 failed: `tests/facts/search/test_planning.py::
  test_a_skipped_comparison_retried_through_an_analysis_line_is_counted` and
  `::test_retries_at_several_nodes_and_a_summed_round`. Both pass when run alone (6 passed in
  `test_planning.py`); they time real searches, the load slowed them, and this packet does not
  touch the fact engine.
- `ruff check` and `ruff format --check` on `src` and `tests`: clean.

## 4. Review dispositions

(none yet)
