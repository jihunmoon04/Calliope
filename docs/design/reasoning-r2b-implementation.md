# Reasoning — packet R2b implementation: catalogue v1 and `label_v1`

Status: **rev. 1 — awaiting independent R2b review**.
Date: 2026-10-10. Design: [`reasoning-r2-design.md`](reasoning-r2-design.md) rev. 11 (R2-D, all
of §1–§8) and [`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 10 (R0-D §7.3, §8.5, §11).
Base: `main @ b723ce1` (R2a merged, #59).

R2 is split like F4: R2a (merged) is the machinery; **R2b** (this packet) is catalogue v1 — the
21 templates of R2-D — the observations `line_material` and `played_edge`, and `label_v1`
(GREAT, MISS; no BRILLIANT, R2-D E10).

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `reasoning/findings.py` | the typed findings of R2-D §1.7 (`Outcome`, `DecisiveEvent`, `MaterialFinding`, `MateFinding`, `ComparisonFinding`, `MechanismFinding`, `DefenceFinding`, `HangingFinding`, `ForcingFinding`, `AlternativeFinding`, `OfferFinding` with `Fate`, `CompensationFinding`, `PreventsFinding`) and the `line_material` operand `LineMaterial` |
| `reasoning/lines.py` | R2-D §1 over lines of S: `read_line` (window, per-ply balances from P, moves), `outcome` (§1.3), the outcome order `compare`, the decisive ply and event (§1.5), the baseline veto (§1.4), `unsafe_v1` (§1.6), exposure continuity (§1.6a), `fact_ref` |
| `reasoning/observer.py` | `scored(view, subject, search_id)` — steps 2–6 of `quality_v1` on the pinned S (`judge` delegates to it); the observations `line_material` and `played_edge` (R2-D §2) |
| `reasoning/controller.py` | round 0 records `standard_lines`, `line_material`, `played_edge` |
| `reasoning/catalogue/` | `base.py` (fields, targets, scopes, verdict helpers of R2-D §3.0); `mates.py` (§3.3–§3.6); `material.py` (§3.1, §3.2); `functions.py` (`forcing_v1`, `only_move_v1`, `prevents_v1`); `sacrifice.py` (§3.11: candidates, exchange runs, fates, the three claims); `mechanisms.py` (§3.7); `hanging.py` (§3.8, §3.8a, §3.8b); `comparison.py` (§3.12); `CATALOGUE_V1` in the registry order of R2-D §6 |
| `reasoning/labels.py` | `Label`, `LabelKind`, `label_v1` (R0-D §11, R2-D §5.2) |
| `reasoning/runner.py` | `Reasoner(fact_engine)` defaults to `CATALOGUE_V1`; `Analysis.labels` |
| `reasoning/graph.py` | the relation type is `ClaimRelation` (§2.9) |
| `reasoning/encoding.py` | the registry also holds the findings, labels, `Claim`, `Verdict`, `ClaimRelation`, `Observation`, `Judgement`, `LineScore` |
| `reasoning/verification.py` | `ALTERNATIVE_OF` reads an engine line's first move from its search (§2.8) |

## 2. Implementation decisions within the design

1. **Package layout.** R0-D §3.2 planned `hypotheses/` with one module per template; the templates
   live in `reasoning/catalogue/`, grouped by kind (the R2a contract module `hypotheses.py`
   stays). The shared definitions (`lines.py`) and findings (`findings.py`) sit beside the
   observer, which reads them for `line_material`.
2. **Template versions** are `"1"`; the names carry `_v1` as R2-D names them. Changing a
   definition changes the version and the build identity (R0-D §8.4).
3. **Windows are operands.** The window cap `pv_plies` is a budget value the templates do not
   see (`verify(h, view)`), so the observer fixes each window at round 0 (R2-D §1.3) and the
   templates copy the window segments `LineSegment(L, 0, k)` into their operands; verification
   re-reads the line over that window. The target stays `seg(L)` (all attached plies, R2-D §3.0)
   and the scope records `plies = k`. In v1 no line grows after round 0 (no template raises a
   `LineNeed`), so the window read at verification is the observer's.
4. **`line_material` covers every line of S** — `Lp`, `L1`, then the others by rank — and records
   one `FactRef("move", N_i, ("events", j))` per capture or promotion. R2-D §2 lists the standard
   lines; `sacrifice_offer_v1` and `prevents_v1` need the other lines' windows (R2-D §7 counts
   them). Amendment recorded in R2-D §12.
5. **`played_edge` is observed for every target move**, also when the judgement is
   INCONCLUSIVE: it is the origin of the exact templates, which need no judgement (R2-D §3.0).
6. **Mechanism operands** are `(X.id, window)`; R2-D §3.7 lists `(X.id)`. Verification receives
   no claims, so a mechanism recomputes `X`'s decisive event from the same window (a pure
   function of it: the same victim, capturer and ply). `left_en_prise_v1` also carries `L1`'s
   window (rule 2).
7. **The judgement in verification** is re-read with `scored(view, subject, S)` on the search the
   target names — the pinned S (R0-D R0-I1), never `view.basis()`.
8. **`ALTERNATIVE_OF` between engine lines from their anchor** compares the lines' first moves as
   the search reports them (`EngineLineFact.move`), so a line cut before its first ply still has
   its move (R2-D §8.6f: `better_move_v1` rests on `mate_allowed_v1` with `L1` cut). R2a read the
   first edge, which a zero-ply line does not have. Amendment recorded in R0-D §29.
9. **`ClaimRelation`.** R0-D §10.2's `Relation` is named `ClaimRelation` in code: the canonical
   encoding names types by class name, and the fact registry already holds the geometry
   `Relation`. Amendment recorded in R0-D §29.
10. **Missing outcomes.** A line of S with no record at P is `MISSING(NOT_COMPUTED(NOT_ATTACHED))`;
    a missing `material` record is `MISSING(NOT_COMPUTED(material))`; a cut line with `r = 0` is
    `MISSING(LINE_TOO_SHORT)` unless its score is a mate (R2-D §1.3).
11. **Sacrifice fate, step 4.** R2-D does not say how an *unfinished* exchange of another of the
    mover's pieces counts in "no equal loss elsewhere". It makes the fate `UNDECIDED` — the piece
    is not yet shown to be kept — so an offer is never SUPPORTED over a line whose other losses
    are still running, and never REFUTED by it either.
12. **`sacrifice_compensated_v1` rule 3** reads its parenthetical as the test: every compared line
    is not a mate for the mover, or a slower one. A compared line with a non-mate score counts as
    "not a mate" whatever its window shows (the mate outcome comes from the score, R2-D §1.3).
13. **Proposal guards that read a record** (`newly_unsafe_v1`, `left_en_prise_v1` read `pieces` at
    P) do not propose when the record is missing. P is an input node with every family eager, so
    this does not occur after round 0.
14. **`better_move_v1` waits** until `material_loss_v1` — and `mate_allowed_v1` when its proposal
    condition holds — has a final claim on `Lp` ("every consequence hypothesis on `Lp` is final",
    R2-D §3.12); templates see only final claims, and those consequences never need evidence.
15. **Mechanism needs** are the missing records at the node where the scan stops (R2-D §3.7 rule
    1); later nodes are read in the next round.
16. **Labels** are `Analysis.labels`; a label's edges to its grounds are `Label.grounds` until
    the stored graph (R4) writes them.
17. **The `SearchMoveRef` citation** for a best line cut before its first ply (R2-D §3.1
    evidence) is left to the renderer (R3): the finding's best outcome has 0 plies and the search
    names the move.
18. **Test engine.** The scripted engine takes explicit PVs and keys positions without clocks
    (the engine input restarts the move counters at the window start).

## 3. Evidence

| Check | Result |
| --- | --- |
| `tests/reasoning/test_catalogue_consequences.py` (R2-D §3.1–§3.6, §3.9–§3.13, §5.2): a loss with its comparison and `COMPARES_WITH`; a loss the best line shares (REFUTED, no premise); an open window; a drawn best line (`UNSTABLE`); the baseline veto (4.Bxc6 dxc6; 1.d4 e5 2.dxe5 Bb4+ 3.Bd2 Bxd2+ 4.Qxd2); a gain; a promotion without capture (no mechanism); Black as mover; mate delivered, found (mating edge), allowed in one (exact, witness) with mate allowed and `better_move_v1` on it, with no judgement (no WDL); mate missed (`SearchMoveRef`); a best line cut before its first ply (mate score decides; `ALTERNATIVE_OF` across it); a cut line with a material outcome (`LINE_TOO_SHORT`); `only_move_v1` by the margin, without rank 2, on a comparison S (`SCOPE_SHORT`); `prevents_v1` SUPPORTED and refuted twice; GREAT; MISS after the opponent's blunder and none without it; no BRILLIANT | 23 passed |
| `tests/reasoning/test_catalogue_mechanisms.py` (R2-D §3.7, §3.8–§3.8b): the knight fork after an unrelated double attack (`EXPLAINS`) and on a piece already losable (`ASSOCIATED_WITH`); a capture-fork; a fork whose capture another piece makes; a pin walked into; a pin decided in round 1 after `NEEDS_EVIDENCE` past the round-0 ensure, and `BUDGET` without ensure nodes; a skewer; a discovered check (at `i = 0`); a removed defender (`DEFENDER_MOVED`, `LINE_BLOCKED`), exact scope, no `CAUSES`; newly unsafe (`MOVED_INTO_ATTACK`, `LINE_OPENED`, a capturer attacking only later); left en prise; a best line losing it too; a piece leaving and returning (`ASSOCIATED_WITH`) | 15 passed |
| `tests/reasoning/test_catalogue_sacrifice.py` (R2-D §3.11, §8.6g, §8.7, §8.7a): a queen offer with a mate return (offer, sound, compensated; keeping fates; witnesses); a mate return as fast as a keeping mate (REFUTED); a forced loss; a line cut right after the capture (`LINE_TOO_SHORT`); mated alternatives (GIVEN_UP); alternatives too short (UNDECIDED); a knight lost everywhere and a queen offer at ply 4; WDL saturation (sound SUPPORTED, compensated REFUTED); a material return strictly above and below the keeping lines; an OPEN keeping line; fates: in-between check and quiet move trades (TRADED by the recapture extension), a queen lost for nothing, an exchange still running, the desperado fork (GIVEN_UP) | 15 passed |
| `tests/reasoning/test_catalogue_lines.py` (R2-D §1, §6, §8.2, §8.6c, §8.6e, §8.10): `unsafe_v1` (lower attacker, outnumbered, equal defended), an absent piece, a missing record; the outcome order (11 cases, both directions); decisive plies (capture-fork, capture then main loss then partial recovery); a capture-promotion as one ply; exposure failing on a present record before a missing one, `UNDECIDED` otherwise, `ROUND_LIMIT`; the registry order; a re-run and a shuffled registry give the same bytes; every claim encodes; no `LineNeed`, no `CAUSES`; every engine target names S | 23 passed |
| `tests/reasoning` (R1, R2a, R2b), `tests/facts` without the 400-game fuzz, boundaries | 508 passed, 8 skipped (real Stockfish, gated) |
| `ruff check`, `ruff format` (redesign packages) | pass |

Not covered by a scenario in rev. 1 (R2-D §8): a discovery whose blocker moves along the ray
(5); several candidates at one node and a captured actor (`Absent`) (5); `DEFENDED_MOVED`,
`DEFENDER_CAPTURED` and a redundant defender (6); a piece moving from one attacked square to
another and a castling rook (6a); an earlier offer re-credited and a trade longer than the
4-ply cap (3); a keeping line ending `DRAWN` (7a: an `OPEN` keeping line covers rule 5's
undecided branch); a capture at ply `j` that ends the game (7a).
