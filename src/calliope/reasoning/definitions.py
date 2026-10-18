"""The reasoning definitions registry (DF-D §2–§6): reasoning's names, stated once, with the fact
engine's entries re-exported (`calliope.facts.FACT_DEFINITIONS`).

Thresholds read their values from the modules that use them, so the registry cannot drift from
the code; `REGISTRY_DIGEST` enters the reasoning build (DF-D §6.1).
"""

from __future__ import annotations

from calliope.facts import FACT_DEFINITIONS, FACT_REASONS, Definition, definitions_digest
from calliope.reasoning import labels, lines, observer, planner, render
from calliope.reasoning.catalogue import exchange, functions, material, mechanisms, sacrifice
from calliope.reasoning.request import ReasoningBudget
from calliope.reasoning.verification import REASONS


def _d(id_, kind, statement, **kw) -> Definition:
    return Definition(id_, kind, statement, **kw)


# -- units (DF-D §3.1) ------------------------------------------------------------------------------

UNITS = [
    _d("unit.cp_white", "unit", "Centipawns from White's view (`calliope_result_v1` scores)."),
    _d(
        "unit.cp_mover",
        "unit",
        "Centipawns from the mover's view (thresholds such as GAIN_CP_PER_POINT).",
    ),
    _d("unit.mate_white", "unit", "Moves to mate, positive when White mates."),
    _d(
        "unit.expected_2000",
        "unit",
        "Expected points in 1/2000 of a game (1000 = a draw), the mover's view; `quality_v1` reads them from the WDL, `quality_v2` from a curve.",
    ),
    _d("unit.points_v1", "unit", "Material points under `points_v1`."),
    _d(
        "unit.permille_white",
        "unit",
        "WDL shares in fixed colours — white_win, draw, black_win — 1000 in all.",
    ),
    _d("unit.plies", "unit", "Half-moves."),
    _d("unit.moves", "unit", "Full moves (a mate in n)."),
    _d("unit.count", "unit", "A number of items (moves, replies, pieces)."),
]

# -- verdicts, scopes, checks, relations (DF-D §4) -------------------------------------------------

STATUSES = [
    _d(
        "SUPPORTED",
        "status",
        "The template's predicate holds within its scope. It does not say that it caused the result: only an EXPLAINS or CAUSES relation whose causal check passed says that, and for a material consequence the ATTRIBUTED check says whether the move brought it about.",
    ),
    _d(
        "REFUTED",
        "status",
        "The predicate is false within the scope, or a named filter rule of the template refuses it (`refuted_by`). It does not prove the opposite outside the scope.",
    ),
    _d(
        "INCONCLUSIVE",
        "status",
        "The evidence could not decide; the reason is a closed code. Nothing follows about the predicate.",
    ),
    _d(
        "NEEDS_EVIDENCE",
        "status",
        "Never final: the claim waits for records and is closed INCONCLUSIVE at the last round.",
    ),
]
QUANTIFIERS = [
    _d(
        "specific_line",
        "quantifier",
        "The predicate holds along this one engine line over the stated plies; other replies are not considered.",
    ),
    _d("persistence", "quantifier", "The predicate holds at every node of the stated span."),
    _d(
        "exists_response",
        "quantifier",
        "Some reply in the stated population satisfies the predicate.",
    ),
    _d(
        "all_responses",
        "quantifier",
        "Every reply in the stated population satisfies the predicate.",
    ),
    _d(
        "exists_alternative",
        "quantifier",
        "Some alternative move in the stated population satisfies the predicate.",
    ),
    _d(
        "all_alternatives",
        "quantifier",
        "Every alternative move in the stated population satisfies the predicate.",
    ),
    _d("selected_alternatives", "quantifier", "The named alternatives satisfy the predicate."),
    _d("population.explicit", "quantifier", "The moves listed."),
    _d(
        "population.engine_reported",
        "quantifier",
        "The lines the named search reported (its MultiPV).",
    ),
    _d(
        "population.engine_ranked",
        "quantifier",
        "The moves the named search ranked, its whole search behind the ranking.",
    ),
    _d("population.legal", "quantifier", "Every legal move."),
    _d("basis.exact", "quantifier", "Proved from the rules and the definitions alone; no engine."),
    _d("basis.engine", "quantifier", "Proved from the named searches at their depth and MultiPV."),
]
CHECKS = [
    _d(
        "REALIZED",
        "check",
        "The mechanism is what delivered the material: the claim may EXPLAIN its consequence. Failed: the configuration occurred (ASSOCIATED_WITH) but did not deliver it.",
    ),
    _d(
        "COUNTERFACTUAL",
        "check",
        "Without the claimed cause the consequence does not happen: the claim may CAUSE it.",
    ),
    _d(
        "ATTRIBUTED",
        "check",
        "`concession_v1`: the lost piece was exposed before the loser's own choices after the reply, or the loser's exposing move was forced (only legal move, every other move allows mate in one, in check no answer saves the piece) or an exchange linked to the loss (EF-D §15 A3). Passed means the stated static rules hold, not a counterfactual proof; failed means not shown to be forced by the move, not that the loser could keep the material.",
        source="EF-D §3, §15",
    ),
]
RELATIONS = [
    _d(
        "derived_from",
        "relation",
        "The claim was proposed from this claim, observation or judgement.",
    ),
    _d(
        "associated_with",
        "relation",
        "The claim co-occurs with the target; no causal check passed.",
    ),
    _d(
        "explains",
        "relation",
        "The claim's REALIZED check passed: it delivered the target's result.",
    ),
    _d("causes", "relation", "The claim's COUNTERFACTUAL check passed."),
    _d("enables", "relation", "The claim makes the target possible."),
    _d("prevents", "relation", "The claim stops the target."),
    _d("compares_with", "relation", "The claim compares the played move with the target's line."),
    _d(
        "qualifies",
        "relation",
        "An INCONCLUSIVE claim on a premise of the target: what could not be confirmed.",
    ),
]

# -- policies and label rules ----------------------------------------------------------------------

POLICIES = [
    _d(
        "quality_v1",
        "policy",
        "The grade from the expected-points loss against rank 1 of the comparison search, expected points read from the engine's WDL; bands EXCELLENT < 40, GOOD < 100, INACCURACY < 200, MISTAKE < 400 (1/2000).",
        source="R1",
    ),
    _d(
        "quality_v2",
        "policy",
        "As `quality_v1`, expected points from a rating-aware score curve (a table by pool, time class and band, or a logistic scale).",
        source="Q-D, QM-D",
    ),
    _d(
        "label_v1",
        "policy",
        "Labels FORCED, GREAT and MISS from the grade and the claims.",
        source="R2b",
    ),
    _d(
        "label_v2",
        "policy",
        "Labels FORCED, GREAT (without routine replies), provisional BRILLIANT and MISS (by expected points).",
        source="LV-D, MV-D",
    ),
    _d(
        "selection_v1",
        "policy",
        "Which claims the explanation states: one consequence, its explaining mechanism, one function, one comparison and its detail, up to two pending sentences.",
        source="R3-D §1",
    ),
    _d(
        "see_v1",
        "policy",
        "Static exchange evaluation (`exchange_v1.PieceExchange.gain`).",
        source="F6-D",
    ),
    _d(
        "exposed_v1",
        "policy",
        "A piece is exposed when `see_v1` gives the opponent at least one point; for a side in check, when the piece has no safe move.",
        source="EF-D §4, §15 A1",
        depends_on=("see_v1",),
    ),
    _d(
        "concession_v1",
        "policy",
        "The ATTRIBUTED check of a material claim (see ATTRIBUTED).",
        source="EF-D §3",
        depends_on=("exposed_v1",),
    ),
    _d(
        "trade_pairs_v1",
        "policy",
        "Plies i, i+1 that both capture, neither promoting, where i+1 takes the piece that moved at i on its square for equal points: they do not move the balance the named decisive event reads.",
        source="EF-D §2",
    ),
    _d(
        "obs_v2",
        "policy",
        "The round-0 observations: standard_lines (Lp and L1 over their windows), line_material (each line's balances, outcome and trade-reduced decisive event), played_edge.",
        source="R2-D §2, EF-D §2",
    ),
    _d("phrases_en_v1", "policy", "The English phrasebook of the renderer.", source="R3-D"),
]
LABEL_RULES = [
    _d("forced_v1", "label_rule", "FORCED: the move is the only legal move."),
    _d(
        "great_p2",
        "label_rule",
        "GREAT (provisional): the only good move by `only_move_v1`, not a routine reply (a recapture, a check answer the engine ranks alone).",
        provenance="provisional",
        source="LV-D",
    ),
    _d(
        "brilliant_p2",
        "label_rule",
        "BRILLIANT (provisional): a best, excellent or good move that offers a piece the opponent can take (`piece_offer_v1`) and still holds after the capture (`capture_holds_v1`), when the mover was not winning anyway.",
        provenance="provisional",
        source="LV-D §5, §15",
    ),
    _d("miss_v1", "label_rule", "MISS (v1 rule).", source="R2b"),
    _d(
        "miss_p2",
        "label_rule",
        "MISS (provisional): the opponent's previous move lost at least MISS_OPPORTUNITY and this move loses at least MISS_LOSS (`missed_gain_v1`).",
        provenance="provisional",
        source="MV-D",
    ),
]

# -- templates (DF-D §2.1, §4.1) -------------------------------------------------------------------

T = "template"
TEMPLATES = [
    _d("mate_delivered_v1", T, "The move mates (exact)."),
    _d("mate_found_v1", T, "Along Lp the mover mates (a mate score for the mover)."),
    _d(
        "mate_in_one_allowed_v1",
        T,
        "After the move the opponent has a mate in one (exact: `status.mating_moves`).",
    ),
    _d("mate_allowed_v1", T, "Along Lp the opponent mates, and along L1 it does not."),
    _d("mate_missed_v1", T, "L1 mates for the mover and Lp does not."),
    _d(
        "material_loss_v2",
        T,
        "Along Lp's window the mover's balance from P ends at least 1 point down and settled, and L1 loses less; the amount is the smaller of the two differences; the decisive event is trade-reduced; with the ATTRIBUTED check.",
        source="R2-D §3.1, EF-D §3.6",
    ),
    _d(
        "material_gain_v3",
        T,
        "Along Lp's window the mover's balance from P ends at least 1 point up and settled (and up from the baseline veto), and Lp's score is at least GAIN_CP_PER_POINT per point when the line's own decisive event is after the reply (`material_gain.score_check`); the named event is trade-reduced; with the ATTRIBUTED check.",
        source="R2-D §3.2, EA-D §2, EF-D §3.6",
    ),
    _d(
        "checks_draw_v1",
        T,
        "The played move's line is a checking draw by either side (threefold, fivefold, repeated or scored by WDL), and the best line is not the same side's checking draw.",
        source="EV-D §2.2",
    ),
    _d(
        "forcing_v1",
        T,
        "The move gives check, or leaves a single legal reply (exact).",
        source="R2-D §3.9",
    ),
    _d(
        "check_answer_v1",
        T,
        "The move is played out of check: a king move, a capture of the checking piece (en passant included) or a block (exact).",
        source="EF-D §5",
    ),
    _d(
        "only_move_v1",
        T,
        "Rank 2 of the unrestricted search loses at least ONLY_MOVE_MARGIN against rank 1.",
        source="R2-D §3.10",
    ),
    _d(
        "sacrifice_offer_v1",
        T,
        "Along Lp the mover gives up material (balance at most GIVE_UP after the offer and its next ply) while a reported alternative keeps it.",
        source="R2-D §3.11",
    ),
    _d(
        "sacrifice_sound_v1",
        T,
        "After the offer the engine still holds the position: at least SOUND_EXPECTED expected points (an evaluation, not a return).",
        source="R2-D §3.11",
    ),
    _d(
        "sacrifice_compensated_v2",
        T,
        "The offer's line ends in mate, or wins back more than the keeping alternatives among those reported (a concrete return). A keeping line whose material is open is below a mate when its engine score is no mate for the mover: the finding is then `mate_over_scores`, an evaluation of that line, not its decided outcome.",
        source="R2-D §3.11; MS-D §3",
    ),
    _d(
        "piece_offer_v1",
        T,
        "The move offers a piece (net at least OFFER_MIN by `see_v1`) the opponent can take, and the capture survey exists; it does not say the offer is sound.",
        source="LV-D §5–§6.1",
    ),
    _d(
        "capture_holds_v1",
        T,
        "After the opponent takes the offered piece, the mover's best line holds at least NOT_BAD expected points.",
        source="LV-D §6.2",
    ),
    _d(
        "rescue_v1",
        T,
        "The move saves a piece that was exposed (`see_v1`) before it.",
        source="LV-D §4.1",
    ),
    _d(
        "prevents_v1",
        T,
        "Every other reported line is mated or loses material, the played line not.",
        source="R2-D §3.13",
    ),
    _d(
        "fork_v2",
        T,
        "Along the material claim's line, a multi-target attack on the decisive piece began, made by the beneficiary (or walked into by the move); REALIZED when the piece was not exposed before, the forking piece captures it and a second target is of equal or higher rank, a king, or exposed.",
        source="R2-D §3.7, EF-D §4",
    ),
    _d(
        "pin_v2",
        T,
        "An absolute or relative pin on the decisive piece began and held until the capture; REALIZED when the piece was not exposed before.",
        source="R2-D §3.7, EF-D §4",
    ),
    _d(
        "skewer_v2",
        T,
        "A skewer with the decisive piece behind began; REALIZED when it was not exposed before and the slider captures it.",
        source="R2-D §3.7, EF-D §4",
    ),
    _d(
        "discovery_v2",
        T,
        "A blocker of the beneficiary moved and opened a slider's attack on the decisive piece (or gave a discovered check while attacking it); REALIZED when it was not exposed before and the slider (or the blocker) captures it.",
        source="R2-D §3.7, EF-D §4",
    ),
    _d(
        "removed_defender_v2",
        T,
        "The move ended the defence of the piece later lost (defender moved or line blocked) while it stayed attacked; REALIZED when it stayed exposed to its capturer up to the capture.",
        source="R2-D §3.8, EF-D §4",
    ),
    _d(
        "newly_exposed_v1",
        T,
        "The move exposed the piece later lost: it moved onto an attacked square, or a line opened onto it; REALIZED as above.",
        source="R2-D §3.8a, EF-D §4",
    ),
    _d(
        "left_en_prise_v2",
        T,
        "The piece later lost was exposed at P, the move left it there, and the best line does not lose it; REALIZED as above.",
        source="R2-D §3.8b, EF-D §4",
    ),
    _d(
        "better_move_v1",
        T,
        "L1's outcome is better for the mover than Lp's, both decided.",
        source="R2-D §3.12",
    ),
    _d(
        "checks_draw_missed_v1",
        T,
        "The best line is the mover's checking draw and the played line is no checking draw.",
        source="EV-D §2.3",
    ),
    _d(
        "best_stops_reply_v1",
        T,
        "What the best move does about the opponent's reply in Lp, by static exchange: RESCUES the piece the reply takes, DEFENDS it (the reply's capture gains nothing after the best move) or COVERS the reply's square.",
        source="EV-D §3",
    ),
    _d(
        "missed_gain_v1",
        T,
        "In S a reported move beat the played move by at least MISS_LOSS expected points; it proves only that a better move existed.",
        source="MV-D §4",
    ),
    _d(
        "better_alternative_v1",
        T,
        "The played move, graded INACCURACY or worse, is not rank 1 of S, so rank 1 was better.",
        source="EA-D §3",
    ),
]
TEMPLATE_RULES = [
    _d(
        "material_gain.score_check",
        "template_rule",
        "A filter of `material_gain_v3` (EA-D §2 rule 3): refused when the line's own decisive event is at ply 3 or later and Lp's score for the mover is below GAIN_CP_PER_POINT × the amount; `refuted_by` names it. An empirical filter, not a proof the gain is kept.",
        source="EA-D §2",
    ),
    *(
        _d(f"material_loss_v2.rule{i}", "template_rule", s, source="R2-D §3.1, EF-D §3")
        for i, s in (
            (1, "Lp ends in mate: INCONCLUSIVE(MATE_LINE)."),
            (2, "Lp's window is open, missing or drawn: INCONCLUSIVE."),
            (3, "Lp ends level or ahead: REFUTED."),
            (4, "L1 drawn or undecided: INCONCLUSIVE."),
            (6, "L1 loses at least as much: REFUTED."),
            (7, "The ATTRIBUTED check (EF-D §3)."),
        )
    ),
    *(
        _d(f"material_gain_v3.rule{i}", "template_rule", s, source="R2-D §3.2, EA-D §2, EF-D §3")
        for i, s in (
            (1, "Lp ends in mate: INCONCLUSIVE(MATE_LINE)."),
            (2, "Lp's window is open, missing or drawn: INCONCLUSIVE."),
            (3, "Below 1 point from P or from the baseline veto: REFUTED; then the score check."),
            (4, "The ATTRIBUTED check (EF-D §3)."),
        )
    ),
]
FINDINGS = [
    _d(f"finding.{n}", "finding", s)
    for n, s in (
        (
            "Outcome",
            "A line's outcome over its window: MATE (winner, moves), STABLE (delta for the mover, points_v1), DRAWN, OPEN or MISSING (reason).",
        ),
        (
            "DecisiveEvent",
            "The capture or promotion at the ply where the trade-reduced balance reaches its final level and stays on its side of 0.",
        ),
        (
            "LineMaterial",
            "A line's window, outcome, the plies that change material, its decisive event and the baseline veto balances.",
        ),
        ("MaterialFinding", "The amount (points_v1), the decisive event, Lp's and L1's outcomes."),
        ("MateFinding", "Mate in `moves` and the mating move."),
        ("ComparisonFinding", "The best move and the outcomes of the best and the played lines."),
        (
            "MechanismFinding",
            "The configuration's kind, the node where it appeared, the actor and its targets; walked_into when the played move walked into it.",
        ),
        ("DefenceFinding", "The defender whose defence ended, the defended piece and why."),
        (
            "HangingFinding",
            "How the lost piece came to be exposed (moved into attack, line opened, left) and its attackers.",
        ),
        ("ForcingFinding", "Whether the move gives check and the opponent's legal replies."),
        ("AlternativeFinding", "Rank 2's line and its loss (expected_2000)."),
        (
            "OfferFinding",
            "The amount given up, the event, and for each keeping alternative its fate.",
        ),
        (
            "CompensationFinding",
            "The kind of return (mate, material return, engine) and the expected points.",
        ),
        (
            "PreventsFinding",
            "What the other reported lines suffer (mate, material, mixed), how many, and the smallest loss (points_v1).",
        ),
        (
            "PieceOfferFinding",
            "The offered piece, the offer (points_v1), whether it was created, the capture, the capture reply and the best keeping line.",
        ),
        (
            "CaptureHoldsFinding",
            "The reply's line after the capture and the mover's expected points there.",
        ),
        ("RescueFinding", "The rescued piece and its exposure before (points_v1)."),
        ("MissedGainFinding", "The better move and the loss (expected_2000)."),
        (
            "ChecksDrawFinding",
            "The checking side, the draw kind, the checks' segment, their number and where the position repeats.",
        ),
        (
            "ReplyFinding",
            "RESCUES / DEFENDS / COVERS: the best move, the reply, the piece, the square, the boards and the exchange gains (points_v1).",
        ),
        (
            "ConcessionFinding",
            "The lost piece and the origin range (plies) where the loser's own move exposed it; the nodes of the origins.",
        ),
        (
            "CheckAnswerFinding",
            "How the move answers the check (block, capture, king), the checking pieces and the legal move count.",
        ),
        (
            "CausalCheck",
            "A REALIZED, COUNTERFACTUAL or ATTRIBUTED check, passed or failed, with its evidence.",
        ),
    )
]
OBSERVATIONS = [
    _d(
        "observation.standard_lines",
        "finding",
        "Lp (the played move's line) and L1 (rank 1) of S over their windows.",
    ),
    _d(
        "observation.line_material",
        "finding",
        "For each line of S: its window, outcome, material changes, decisive event and veto.",
    ),
    _d("observation.played_edge", "finding", "The played move's edge P → C."),
]

# -- thresholds (DF-D §6.1): values read from the modules ------------------------------------------


def _t(id_, value, unit, statement, provenance="design", source="") -> Definition:
    return Definition(id_, "threshold", statement, unit=unit, value=value, provenance=provenance,
                      source=source)  # fmt: skip


def thresholds() -> list[Definition]:
    """The thresholds with the values the modules hold now (a build reads them when it is made)."""

    budget = ReasoningBudget()
    return [
        _t(
            "GAIN_CP_PER_POINT",
            material.GAIN_CP_PER_POINT,
            "cp_mover",
            "A later-line gain needs Lp's score at least this per point gained.",
            "measured",
            "EA-D E2",
        ),
        _t(
            "ONLY_MOVE_MARGIN",
            functions.ONLY_MOVE_MARGIN,
            "expected_2000",
            "Rank 2 loses at least this for `only_move_v1`.",
            source="R0-D D10",
        ),
        _t(
            "OFFER_MIN",
            exchange.OFFER_MIN,
            "points_v1",
            "The least net offer of `piece_offer_v1`.",
            "provisional",
            "LV-D",
        ),
        _t(
            "NEAR_BEST",
            exchange.NEAR_BEST,
            "expected_2000",
            "BRILLIANT: the move's loss is below this.",
            "provisional",
            "LV-D",
        ),
        _t(
            "NOT_BAD",
            exchange.NOT_BAD,
            "expected_2000",
            "`capture_holds_v1`: expected points after the move and the capture at least this.",
            "provisional",
            "LV-D",
        ),
        _t(
            "WINNING",
            exchange.WINNING,
            "expected_2000",
            "BRILLIANT is withheld when a non-offering line holds at least this.",
            "provisional",
            "LV-D",
        ),
        _t(
            "GIVE_UP",
            sacrifice.GIVE_UP,
            "points_v1",
            "`sacrifice_offer_v1`: the balance after the offer and the mover's next ply at most this.",
            source="R2-D §3.11",
        ),
        _t(
            "TRADED_NET",
            sacrifice.TRADED_NET,
            "points_v1",
            "An exchange netting at least this gives the piece's value back.",
            source="R2-D §3.11",
        ),
        _t(
            "SOUND_EXPECTED",
            sacrifice.SOUND_EXPECTED,
            "expected_2000",
            "`sacrifice_sound_v1`: expected points after the offer at least this.",
            source="R2-D §3.11",
        ),
        _t(
            "MISS_OPPORTUNITY",
            labels.MISS_OPPORTUNITY,
            "expected_2000",
            "MISS: the opponent's previous move lost at least this.",
            "provisional",
            "MV-D",
        ),
        _t(
            "MISS_LOSS",
            labels.MISS_LOSS,
            "expected_2000",
            "MISS and `missed_gain_v1`: this move loses at least this.",
            "provisional",
            "MV-D",
        ),
        _t(
            "VETO_PLIES",
            lines.VETO_PLIES,
            "plies",
            "The baseline veto walks back from P at most this many capturing or checking plies.",
            source="R2-D §1.4",
        ),
        _t(
            "BATCH_NODES",
            mechanisms.BATCH_NODES,
            "count",
            "A mechanism asks, at its first step missing a record, for the missing reads of at most this many steps from there.",
            source="MS-D §2",
        ),
        _t(
            "CHECK_RUN",
            lines.CHECK_RUN,
            "count",
            "A checking draw needs at least this many consecutive checks.",
            source="EV-D §2.1",
        ),
        _t(
            "DRAW_CP",
            lines.DRAW_CP,
            "cp_mover",
            "A checking draw's line scores within ± this.",
            source="EV-D §2.1",
        ),
        _t(
            "DRAW_WDL",
            lines.DRAW_WDL,
            "count",
            "REPEATED and SCORED draws need at least this permille drawn (WDL).",
            source="EV-D §2.1",
        ),
        _t(
            "IMMEDIATE_PLIES",
            render.IMMEDIATE_PLIES,
            "plies",
            "An event at or before this ply is the move's own; later events are the line's.",
            "owner",
            "R3-D §17, A2",
        ),
        _t(
            "MAX_LINE_PLIES",
            render.MAX_LINE_PLIES,
            "plies",
            "Plies of a line quoted in text.",
            source="R3-D H5",
        ),
        _t(
            "MAX_PENDING",
            planner.MAX_PENDING,
            "count",
            "Pending (INCONCLUSIVE) sentences at most.",
            source="R3-D H1",
        ),
        *(
            _t(
                f"BANDS.{name}",
                bound,
                "expected_2000",
                f"A loss below this grades {name} or better (both policies).",
                "design",
                "R1, Q-D",
            )
            for bound, name in observer.BANDS
        ),
        *(
            _t(f"ReasoningBudget.{name}", getattr(budget, name), unit, statement, source="R0-D D8")
            for name, unit, statement in (
                ("max_rounds", "count", "Evidence rounds per target move."),
                ("max_extra_searches", "count", "Extra engine searches per target move."),
                ("max_ensure_nodes", "count", "Nodes per `ensure` round."),
                ("max_tree_nodes", "count", "Tree nodes per analysis."),
                (
                    "pv_plies",
                    "plies",
                    "A line's material window from P (widened to twice this while unsettled).",
                ),
                ("deadline_ms", "count", "The analysis deadline in milliseconds."),
                ("max_hypotheses", "count", "Hypotheses per analysis."),
                ("max_derivation_depth", "count", "Premise chains at most this deep."),
                ("max_fixpoint_passes", "count", "Propose–verify passes per round."),
            )
        ),
    ]


THRESHOLDS = thresholds()

# the lines module and the renderer each name IMMEDIATE_PLIES; one value
assert lines.IMMEDIATE_PLIES == render.IMMEDIATE_PLIES

# -- reasons (DF-D §6.2) ---------------------------------------------------------------------------

_REASON_TEXT = {
    "ROUND_LIMIT": "The round limit was reached with the claim still open.",
    "BUDGET": "The analysis budget ran out.",
    "NEED_UNMET": "A record admitted earlier was still needed.",
    "IRREGULAR_SEARCH": "The engine search was incomplete.",
    "DEADLINE": "The analysis deadline was reached.",
    "UNSTABLE": "The outcome is not settled (a drawn window, or incomparable outcomes).",
    "LINE_TOO_SHORT": "The line ends before its material settles.",
    "MATE_LINE": "The line ends in mate: material is not the measure.",
    "SCOPE_SHORT": "The achieved scope does not cover the target.",
}
assert set(_REASON_TEXT) == REASONS
NOT_COMPUTED = {
    "move": "The family's record was missing at a node the claim reads.",
    "status": "As above, for `status`.",
    "squares": "As above, for `squares`.",
    "material": "As above, for `material`.",
    "draw": "As above, for `draw`.",
    "exchange": "As above, for `exchange`.",
    "wdl": "The line's search reported no WDL.",
    "WDL_UNAVAILABLE": "The line's search reported no WDL (the older spelling of `wdl`).",
    "NO_LINES": "The survey reported no line.",
    "NO_RANK_2": "The search reported no second line.",
    "NOT_ATTACHED": "The line's PV is not attached to the tree.",
    "IN_CHECK": "The exchange test is undefined for a side in check.",
    "FactEngineError": "The fact engine refused the request.",
    "BudgetExceededError": "The fact engine refused the request: its budget.",
    "CrossSearchError": "The fact engine refused the request: a comparison across searches.",
    "EngineError": "The fact engine refused the request: the engine failed.",
    "EngineOutputError": "The fact engine refused the request: unreadable engine output.",
    "EngineUnsupportedError": "The fact engine refused the request: an unsupported engine option.",
}
REASON_DEFINITIONS = [
    *(_d(f"reason.{c}", "reason", s, source="R0-D §9.2") for c, s in sorted(_REASON_TEXT.items())),
    *(
        _d(f"reason.NOT_COMPUTED({c})", "reason", s, source="DF-D §6.2")
        for c, s in sorted(NOT_COMPUTED.items())
    ),
]
NOT_COMPUTED_CODES = frozenset(NOT_COMPUTED)
REASON_CODES = frozenset(REASONS) | {f"NOT_COMPUTED({c})" for c in NOT_COMPUTED}

REASONING_DEFINITIONS: tuple[Definition, ...] = (
    *UNITS, *STATUSES, *QUANTIFIERS, *CHECKS, *RELATIONS, *POLICIES, *LABEL_RULES, *TEMPLATES,
    *TEMPLATE_RULES, *FINDINGS, *OBSERVATIONS, *THRESHOLDS, *REASON_DEFINITIONS,
)  # fmt: skip
DEFINITIONS: tuple[Definition, ...] = (*FACT_DEFINITIONS, *REASONING_DEFINITIONS)
REGISTRY_DIGEST = definitions_digest(DEFINITIONS)


def current_digest() -> str:
    """The registry's digest with the thresholds the modules hold now (DF-D §6.1: a changed
    threshold changes the build)."""

    rest = tuple(d for d in REASONING_DEFINITIONS if d.kind != "threshold")
    return definitions_digest((*FACT_DEFINITIONS, *rest, *thresholds()))


assert len({d.id for d in DEFINITIONS}) == len(DEFINITIONS), "definition ids are unique"
assert FACT_REASONS  # the fact engine's codes are its own entries (`fact_reason.*`)
