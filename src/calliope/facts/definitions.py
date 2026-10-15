"""The fact engine's definitions registry (DF-D §2): every name its records can carry, stated once.

A `Definition` says what holds when the value is present — never what it suggests. The registry
covers each family, the fields of its record and of the records it lists (`PieceFacts`, `Ray`, …),
the value tables, the line-settlement rule, the fact classes, the sentinels and their closed reason
codes. `calliope.reasoning.definitions` adds reasoning's entries and re-exports these.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from calliope.facts.families.material import POINTS_V1_BY_TYPE
from calliope.facts.families.pieces import PIECE_ORDER_RANK
from calliope.facts.flow import SETTLE_PLIES
from calliope.facts.values import FACT_REASONS

# Kinds (DF-D §2.1, as built by DF1): the fact classes, then the kinds of the reasoning entries.
KINDS = (
    "family", "field", "rule", "defined", "attested", "sentinel", "reason", "unit",
    "policy", "template", "template_rule", "check", "label_rule", "threshold", "status",
    "quantifier", "relation", "finding",
)  # fmt: skip
BASES = ("rule", "geometric", "hypothetical", "engine", "count")
PROVENANCES = ("rules", "design", "measured", "provisional", "owner")


@dataclass(frozen=True, slots=True)
class Definition:
    id: str
    kind: str
    statement: str
    basis: str | None = None
    unit: str | None = None
    perspective: str | None = None  # "white" | "mover" | "side_to_move" | "owner"
    value: int | None = None  # thresholds only
    provenance: str = "design"
    source: str = ""
    configuration_only: bool = False
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.id}: unknown kind {self.kind!r}")
        if self.basis is not None and self.basis not in BASES:
            raise ValueError(f"{self.id}: unknown basis {self.basis!r}")
        if self.provenance not in PROVENANCES:
            raise ValueError(f"{self.id}: unknown provenance {self.provenance!r}")


def _fields(family: str, record: str, basis: str | None, rows, source: str, **common):
    """Field entries `<family>.<record>.<field>` from (field, statement[, basis]) rows."""

    out = []
    for row in rows:
        name, statement = row[0], row[1]
        out.append(
            Definition(
                f"{family}.{record}.{name}", "field", statement,
                basis=row[2] if len(row) > 2 else basis, source=source, **common,
            )
        )  # fmt: skip
    return out


GEOM = "geometric"
PIN_NOTE = "an absolutely pinned piece is counted, and flagged in `absolutely_pinned`"

_FAMILIES = [
    Definition(
        "status_v1",
        "family",
        "The game state of a position by the rules: side to move, check, mate, stalemate, insufficient material, and every legal move.",
        "rule",
        source="F1",
    ),
    Definition(
        "material_v1",
        "family",
        "The pieces of each colour by type, and their points under `points_v1`.",
        "count",
        source="F1, A0 §6.2",
    ),
    Definition(
        "draw_v1",
        "family",
        "Draw rules at a node over its known history: the clocks, repetitions of the position, threefold and fivefold, fifty and seventy-five moves.",
        "rule",
        source="F1",
    ),
    Definition(
        "move_v1",
        "family",
        "The move into a node: its notation, the moving piece and its identity, castling, check, mate, and its capture and promotion events.",
        "rule",
        source="F1",
    ),
    Definition(
        "pieces_v1",
        "family",
        f"For every piece: its attack set, attackers and defenders (geometric; {PIN_NOTE}), counts, absolute pins, and for the side to move its legal moves.",
        GEOM,
        source="F2-D §2",
    ),
    Definition(
        "squares_v1",
        "family",
        "For every square: its occupant and the pieces of each colour that attack it (geometric).",
        GEOM,
        source="F2-D §3",
    ),
    Definition(
        "lines_v1",
        "family",
        "Every slider's rays with their occupants, the first blocker, x-rays through one piece, and batteries of two sliders on one line.",
        GEOM,
        source="F2-D §4",
    ),
    Definition(
        "pawns_v1",
        "family",
        "Pawn structure: per pawn isolated, doubled, passed, backward, supporters and phalanx; chains, islands, file states and the squares outside every enemy pawn's forward span.",
        GEOM,
        source="F2-D §5",
    ),
    Definition(
        "king_zone_v1",
        "family",
        "Each king's zone (its square and neighbours) with enemy attackers, its pawn shield, nearby files and flight squares.",
        GEOM,
        source="F2-D §6",
    ),
    Definition(
        "delta_v1",
        "family",
        "What a move changed in side-independent geometry: relation sets keyed by piece identity, with what began and what ended; captured pieces end with `Absent(CAPTURED)`.",
        GEOM,
        source="F2-D §7.1",
    ),
    Definition(
        "same_side_delta_v1",
        "family",
        "Changes between a node and its grandparent, the same side to move: legal destinations, captures, capturable pieces, flight squares and the legal move count.",
        "rule",
        source="F2-D §7.2",
    ),
    Definition(
        "patterns_v1",
        "family",
        "Geometric configurations of both colours — multi-target attacks, relative pins, skewers, discovery lines, sole defenders, back ranks; a configuration, never a result.",
        GEOM,
        source="F3-D §2",
        configuration_only=True,
    ),
    Definition(
        "pattern_delta_v1",
        "family",
        "Which configurations of `patterns_v1` began or ended across a move, by piece identity, and the defences that ended while the defended piece stays attacked.",
        GEOM,
        source="F3-D §4",
        configuration_only=True,
    ),
    Definition(
        "exchange_v1",
        "family",
        "Static exchange evaluation (`see_v1`) of every non-king piece, and for an exposed piece of the side to move, or every piece of a side in check, its safe moves; on request.",
        "rule",
        source="F6-D",
    ),
]

_FIELD_ENTRIES = [
    *_fields(
        "status_v1",
        "StatusFacts",
        "rule",
        [
            ("side_to_move", "The colour to move."),
            ("in_check", "The side to move is in check."),
            ("checkers", "The squares of the pieces giving check."),
            ("checkmate", "The side to move is checkmated."),
            ("stalemate", "The side to move has no legal move and is not in check."),
            (
                "insufficient_material",
                "Neither side can mate by any sequence of legal moves (the rules' material test).",
            ),
            ("legal_move_count", "The number of legal moves of the side to move."),
            ("legal_moves", "Every legal move of the side to move (UCI and SAN), sorted by UCI."),
            (
                "legal_captures",
                "Every legal capture of the side to move, with capturer, victim and landing squares.",
            ),
            ("checking_moves", "The legal moves that give check."),
            ("mating_moves", "The legal moves that mate at once."),
            ("promotions", "The legal promotions."),
        ],
        "F1",
    ),
    *_fields(
        "material_v1",
        "MaterialFacts",
        "count",
        [
            ("white", "White's pieces by type, bishops also by square colour."),
            ("black", "Black's pieces by type, bishops also by square colour."),
            (
                "points",
                "(white, black) under `points_v1`: a counting convention, not a value judgement.",
                "count",
            ),
        ],
        "F1",
    ),
    *_fields(
        "draw_v1",
        "DrawFacts",
        "rule",
        [
            ("halfmove_clock", "Plies since the last capture or pawn move."),
            ("fullmove_number", "The move number."),
            (
                "occurrences",
                "Occurrences of the position in the known history (FIDE repetition identity); `AtLeast` when the history is incomplete.",
            ),
            (
                "threefold_reached",
                "The position occurs a third time: a draw can be claimed (FIDE 9.2).",
            ),
            ("threefold_claimable_by_move", "A legal move would make a threefold claimable."),
            ("fivefold_reached", "The position occurs a fifth time: the game is drawn (FIDE 9.6)."),
            (
                "fifty_move_reached",
                "Fifty moves without capture or pawn move: a draw can be claimed.",
            ),
            (
                "seventy_five_move_reached",
                "Seventy-five moves without capture or pawn move: the game is drawn.",
            ),
        ],
        "F1",
    ),
    *_fields(
        "move_v1",
        "MoveFacts",
        "rule",
        [
            ("uci", "The move in canonical UCI."),
            ("san", "The move in SAN."),
            ("mover", "The colour that moved."),
            ("piece", "The physical identity of the moving piece."),
            ("piece_type", "The moving piece's type before the move."),
            ("from_square", "The square left."),
            ("to_square", "The square reached."),
            ("castling", "The castling side, when the move castles."),
            ("gives_check", "The move gives check."),
            ("gives_mate", "The move mates."),
            (
                "events",
                "The move's capture (victim, square — the victim's square, which differs for en passant), promotion and castling rook transfer.",
            ),
        ],
        "F1",
    ),
    *_fields(
        "pieces_v1",
        "PieceFacts",
        GEOM,
        [
            ("square", "The piece's square.", "rule"),
            ("color", "Its colour.", "rule"),
            ("piece_type", "Its type.", "rule"),
            (
                "attacks",
                "The squares it attacks — empty, friendly, enemy — as python-chess attack sets: a slider stops at, and includes, the first piece.",
            ),
            ("attackers", f"The enemy pieces attacking it; {PIN_NOTE}."),
            ("defenders", f"Its own pieces attacking its square; {PIN_NOTE}."),
            ("attacker_count", "len(attackers).", "count"),
            ("defender_count", "len(defenders).", "count"),
            ("lowest_attacker_types", "The lowest-ranked attacker types under `piece_order_v1`."),
            ("attacked_without_defender", "Attacked and not defended (counts, not the exchange)."),
            (
                "attackers_exceed_defenders",
                "More attackers than defenders (counts, not the exchange).",
            ),
            (
                "absolutely_pinned",
                "The pinner and direction when the piece is pinned to its king by the ray rule (F2-D §2).",
            ),
            ("legal_destinations", "Its legal destinations; side to move only.", "rule"),
            ("legal_moves", "Its legal moves; side to move only.", "rule"),
            (
                "legally_capturable_now",
                "The side to move can capture it now with a legal move.",
                "rule",
            ),
        ],
        "F2-D §2",
    ),
    *_fields(
        "squares_v1",
        "SquareFacts",
        GEOM,
        [
            ("square", "The square.", "rule"),
            ("occupant", "The piece on it, if any.", "rule"),
            ("white_attackers", f"White pieces attacking it; {PIN_NOTE}."),
            ("black_attackers", f"Black pieces attacking it; {PIN_NOTE}."),
            ("white_count", "len(white_attackers).", "count"),
            ("black_count", "len(black_attackers).", "count"),
        ],
        "F2-D §3",
    ),
    *_fields(
        "lines_v1",
        "Ray",
        GEOM,
        [
            ("source", "The slider's square."),
            ("direction", "The unit step of the ray."),
            ("squares", "The ray's squares to the edge, near to far."),
            ("occupants", "The pieces on the ray, near to far."),
            ("edge_empty", "No piece on the ray."),
            ("unblocked", "The squares up to and including the first occupant."),
            ("first_blocker", "The first occupant."),
            ("visible", "The squares the slider attacks along the ray."),
            ("xray", "The first two occupants when the ray passes one piece."),
        ],
        "F2-D §4",
    ),
    *_fields(
        "lines_v1",
        "LinesFacts",
        GEOM,
        [
            ("rays", "Every slider's rays, by source square then direction."),
            ("batteries", "Two sliders of one colour on one line that both move along it."),
        ],
        "F2-D §4",
    ),
    *_fields(
        "pawns_v1",
        "PawnFacts",
        GEOM,
        [
            ("square", "The pawn's square.", "rule"),
            ("color", "Its colour.", "rule"),
            ("isolated", "No own pawn on an adjacent file."),
            ("doubled", "Two or more own pawns on its file (each is flagged)."),
            ("passed", "No enemy pawn on its or an adjacent file strictly ahead of it."),
            ("own_pawn_ahead", "An own pawn on its file strictly ahead."),
            (
                "backward",
                "Not isolated, every own pawn on an adjacent file is ahead of it, and its stop square is attacked by an enemy pawn.",
            ),
            (
                "supporters",
                "Own pawns on an adjacent file one rank behind (its defenders among pawns).",
            ),
            ("phalanx", "Own pawns on an adjacent file on the same rank."),
        ],
        "F2-D §5",
    ),
    *_fields(
        "pawns_v1",
        "PawnsFacts",
        GEOM,
        [
            ("pawns", "Every pawn's facts, by square."),
            (
                "chains",
                "Connected groups (two or more) of the supporter relation; bases have no supporter, heads support none.",
            ),
            ("islands", "Per colour, runs of adjacent files holding own pawns."),
            (
                "files",
                "Per file: pawns of each colour and the state open, semi-open (for one colour) or closed.",
            ),
            (
                "outside_enemy_pawn_cones",
                "Per colour, the squares no enemy pawn's forward span (adjacent files, ranks ahead) contains: no enemy pawn can ever attack them.",
            ),
        ],
        "F2-D §5",
    ),
    *_fields(
        "king_zone_v1",
        "KingFacts",
        GEOM,
        [
            ("color", "The king's colour.", "rule"),
            ("square", "Its square.", "rule"),
            (
                "zone",
                "The king's square and neighbours, each with its enemy geometric attackers; behind a checked king on the checking line a square shows no attacker.",
            ),
            ("shield", "Own pawns on the king's file ±1, one and two ranks in front."),
            ("files_near", "The file states of the king's file ±1."),
            (
                "flight_squares",
                "Legal king destinations for the side to move (castling excluded), or for the other side the neighbours not own-occupied and not enemy-attacked; `kind` says which.",
            ),
        ],
        "F2-D §6",
    ),
    *_fields(
        "delta_v1",
        "DeltaFacts",
        GEOM,
        [
            ("square_control", "Piece → square attack relations that began and ended."),
            ("piece_attacks", "Attacker → victim relations that began and ended."),
            ("piece_defences", "Defender → defended relations that began and ended."),
            (
                "piece_flags",
                "Changes of `attacked_without_defender` and `attackers_exceed_defenders`.",
            ),
            ("pins", "Absolute pins (pinner, pinned, king) that began and ended."),
            ("xrays", "X-rays (slider, first, second) that began and ended."),
            ("batteries", "Batteries that began and ended."),
            (
                "pawn_flags",
                "Changes of the pawn flags of `pawns_v1`; a promoted pawn ends with `Absent(PROMOTED)`.",
            ),
            ("pawn_supports", "Pawn support relations that began and ended."),
            ("files", "Files whose state changed."),
            ("islands", "Colours whose islands changed."),
            ("zone_attacks", "King-zone attacks (king, square, attacker) that began and ended."),
            ("shield", "Shield pawns that began and ended."),
        ],
        "F2-D §7.1",
    ),
    *_fields(
        "same_side_delta_v1",
        "SameSideDelta",
        "rule",
        [
            ("pieces", "The side's pieces at the grandparent and the node, by identity."),
            ("legal_destinations", "Per piece, legal destinations gained and lost."),
            ("legal_captures", "Legal captures gained and lost."),
            (
                "capturable_now",
                "Per piece, whether the opponent could capture it now, before and after.",
            ),
            ("flight_squares", "King flight squares gained and lost."),
            ("legal_move_count", "(grandparent, node) legal move counts."),
        ],
        "F2-D §7.2",
    ),
    *_fields(
        "patterns_v1",
        "PatternsFacts",
        GEOM,
        [
            (
                "multi_target_attacks",
                "A piece attacks two or more enemy pieces (geometric); each target's rank against the actor under `piece_order_v1`. Defences and values are not considered.",
            ),
            (
                "relative_pins",
                "On a slider's ray the first two occupants are enemy pieces and the farther one outranks the nearer (`piece_order_v1`), the farther not a king.",
            ),
            (
                "skewers",
                "On a slider's ray the first two occupants are enemy pieces and the nearer one outranks the farther.",
            ),
            (
                "discovery_lines",
                "On a slider's ray the first occupant is the slider's own piece and the second an enemy piece.",
            ),
            (
                "sole_defenders",
                "One piece is the only defender of two or more attacked pieces (kings excluded).",
            ),
            (
                "back_ranks",
                "A king on its first rank whose three forward squares are each own-occupied or enemy-attacked, at least one own-occupied. Access by enemy pieces to the rank is not considered.",
            ),
        ],
        "F3-D §2",
        configuration_only=True,
    ),
    *_fields(
        "pattern_delta_v1",
        "PatternDeltaFacts",
        GEOM,
        [
            ("multi_target_attacks", "Per actor, the target set before and after (by identity)."),
            ("relative_pins", "Relative pins (slider, front, back) that began and ended."),
            ("skewers", "Skewers that began and ended."),
            ("discovery_lines", "Discovery lines that began and ended."),
            ("sole_defenders", "Per defender, the defended set before and after."),
            ("back_ranks", "Back-rank configurations that changed."),
            (
                "defences_ended_under_attack",
                "Defences that ended while the defended piece is still attacked, with the reason: defender captured, defender moved, defended moved, line blocked.",
            ),
        ],
        "F3-D §4",
        configuration_only=True,
    ),
    *_fields(
        "exchange_v1",
        "PieceExchange",
        "rule",
        [
            ("square", "The piece's square."),
            ("color", "Its colour."),
            ("piece_type", "Its type."),
            (
                "gain",
                "`see_v1`: what the opponent wins by starting captures on the piece — legal captures, least valuable first, either side may stop; for the side to move with the turn passed; `NotApplicable(IN_CHECK)` for a side in check.",
                "hypothetical",
            ),
            (
                "first_capture",
                "The first capture of that exchange (UCI) when the gain is positive.",
            ),
            (
                "hypothetical",
                "The gain was computed with the turn passed (the piece's side is to move).",
            ),
            (
                "safe_moves",
                "For an exposed piece of the side to move, or any piece of a side in check: the legal moves after which it is not exposed; `NotApplicable(NOT_EXPOSED)` otherwise, `NotObserved` for the other side.",
            ),
        ],
        "F6-D §2",
    ),
]

# the records the families' records hold (DF1 review B1: every field of every record type)
RELATION = [
    ("square", "The related piece's square.", "rule"),
    ("piece_type", "Its type.", "rule"),
    ("absolutely_pinned", "It is absolutely pinned (the relation still counts it)."),
]
BY_COLOR = [("white", "The value for White.", "rule"), ("black", "The value for Black.", "rule")]
FILE_FACTS = [
    ("file", "The file.", "rule"),
    ("white_pawns", "White pawns on it.", "count"),
    ("black_pawns", "Black pawns on it.", "count"),
    ("state", "`FileState`: open, semi-open for White or Black, or closed."),
]
SET_CHANGE = [
    ("began", "The relations (by piece identity) present after the move and not before."),
    ("ended", "The relations present before the move and not after."),
]
PIECE_PAIR = [
    ("source", "The relation's first piece (attacker, defender, supporter), by identity.", "rule"),
    ("target", "Its second piece (victim, defended, supported), by identity.", "rule"),
]


def _enum(family: str, name: str, statement: str, source: str) -> Definition:
    return Definition(f"{family}.{name}", "field", statement, source=source)


_HELPERS = [
    *_fields(
        "status_v1",
        "LegalMove",
        "rule",
        [("uci", "The move in canonical UCI."), ("san", "The move in SAN.")],
        "F1",
    ),
    *_fields(
        "status_v1",
        "LegalCapture",
        "rule",
        [
            ("uci", "The capture in canonical UCI."),
            ("capturer_square", "The capturing piece's square."),
            ("capturer_type", "Its type."),
            (
                "victim_square",
                "The captured piece's square (differs from the landing square for en passant).",
            ),
            ("victim_type", "Its type."),
            ("landing_square", "The square the capturer lands on."),
            ("en_passant", "The capture is en passant."),
            ("promotion", "The promotion type, when the capture promotes."),
        ],
        "F1",
    ),
    *_fields(
        "material_v1",
        "MaterialCount",
        "count",
        [
            ("pawns", "Pawns."),
            ("knights", "Knights."),
            ("bishops", "Bishops."),
            ("rooks", "Rooks."),
            ("queens", "Queens."),
            ("light_square_bishops", "Bishops on light squares."),
            ("dark_square_bishops", "Bishops on dark squares."),
        ],
        "F1",
    ),
    *_fields(
        "move_v1",
        "Capture",
        "rule",
        [
            ("piece", "The captured piece's identity."),
            ("piece_type", "Its type."),
            ("square", "The victim's square (the landing square except en passant)."),
            ("en_passant", "The capture is en passant."),
        ],
        "F1",
    ),
    *_fields(
        "move_v1",
        "Promotion",
        "rule",
        [
            ("piece", "The promoting pawn's identity (it continues as the new piece)."),
            ("to", "The type promoted to."),
        ],
        "F1",
    ),
    *_fields(
        "move_v1",
        "RookTransfer",
        "rule",
        [
            ("piece", "The castling rook's identity."),
            ("from_square", "The square it leaves."),
            ("to_square", "The square it reaches."),
        ],
        "F1",
    ),
    _enum("move_v1", "CastlingSide", "The castling side: kingside or queenside.", "F1"),
    *_fields(
        "pieces_v1",
        "PiecesFacts",
        GEOM,
        [("pieces", "Every piece's `PieceFacts`, by square.")],
        "F2-D §2",
    ),
    *_fields(
        "pieces_v1",
        "Footprint",
        GEOM,
        [
            ("empty", "Attacked squares that are empty."),
            ("friendly", "Attacked squares holding own pieces."),
            ("enemy", "Attacked squares holding enemy pieces."),
        ],
        "F2-D §2",
    ),
    *_fields("pieces_v1", "Relation", GEOM, RELATION, "F2-D §1.4"),
    *_fields(
        "pieces_v1",
        "Pin",
        GEOM,
        [
            ("pinner", "The pinning slider's square."),
            ("direction", "The unit step from the king toward the pinner."),
        ],
        "F2-D §2",
    ),
    *_fields(
        "squares_v1",
        "SquaresFacts",
        GEOM,
        [("squares", "Every square's `SquareFacts`, a1 … h8.")],
        "F2-D §3",
    ),
    *_fields(
        "squares_v1",
        "Occupant",
        "rule",
        [("color", "The occupant's colour."), ("piece_type", "Its type.")],
        "F2-D §3",
    ),
    *_fields("squares_v1", "Relation", GEOM, RELATION, "F2-D §1.4"),
    *_fields(
        "lines_v1",
        "RayOccupant",
        "rule",
        [
            ("square", "The occupant's square."),
            ("color", "Its colour."),
            ("piece_type", "Its type."),
        ],
        "F2-D §4",
    ),
    *_fields(
        "lines_v1",
        "XRay",
        GEOM,
        [
            ("squares", "The ray's squares up to the second occupant."),
            ("first", "The first occupant (the piece x-rayed through)."),
            ("second", "The second occupant."),
        ],
        "F2-D §4",
    ),
    *_fields(
        "lines_v1",
        "Battery",
        GEOM,
        [
            ("pieces", "The two sliders' squares."),
            ("line", "The direction they share."),
        ],
        "F2-D §4",
    ),
    *_fields(
        "pawns_v1",
        "PawnChain",
        GEOM,
        [
            ("color", "The chain's colour.", "rule"),
            ("squares", "Its pawns."),
            ("bases", "Its pawns without a supporter."),
            ("heads", "Its pawns supporting none."),
        ],
        "F2-D §5",
    ),
    *_fields("pawns_v1", "FileFacts", GEOM, FILE_FACTS, "F2-D §5"),
    _enum(
        "pawns_v1",
        "FileState",
        "A file's state: open (no pawns), semi_open_white (no white pawn, a black one), semi_open_black (the reverse), closed (pawns of both colours).",
        "F2-D §5",
    ),
    *_fields("pawns_v1", "ByColor", None, BY_COLOR, "F2-D §5"),
    *_fields(
        "king_zone_v1",
        "ZoneSquare",
        GEOM,
        [
            ("square", "A square of the zone.", "rule"),
            ("attackers", "The enemy pieces attacking it (geometric)."),
        ],
        "F2-D §6",
    ),
    *_fields(
        "king_zone_v1",
        "FlightSquares",
        None,
        [
            ("kind", "`FlightKind`: legal (the side to move) or geometric (the other side)."),
            ("squares", "The flight squares."),
        ],
        "F2-D §6",
    ),
    _enum(
        "king_zone_v1",
        "FlightKind",
        "How flight squares are found: legal (king moves of the side to move, castling excluded) or geometric (neighbours neither own-occupied nor enemy-attacked).",
        "F2-D §6",
    ),
    *_fields("king_zone_v1", "ByColor", None, BY_COLOR, "F2-D §6"),
    *_fields("king_zone_v1", "Relation", GEOM, RELATION, "F2-D §1.4"),
    *_fields("king_zone_v1", "FileFacts", GEOM, FILE_FACTS, "F2-D §5"),
    *_fields("delta_v1", "SetChange", GEOM, SET_CHANGE, "F2-D §7.1"),
    *_fields(
        "delta_v1",
        "FlagChange",
        GEOM,
        [
            ("piece", "The piece, by identity.", "rule"),
            ("before", "Its flags before the move."),
            ("after", "Its flags after, or `Absent(CAPTURED / PROMOTED)`."),
        ],
        "F2-D §7.1",
    ),
    *_fields("delta_v1", "PiecePair", GEOM, PIECE_PAIR, "F2-D §7.1"),
    *_fields(
        "delta_v1",
        "SquareControl",
        GEOM,
        [
            ("piece", "The attacking piece, by identity.", "rule"),
            ("square", "The square it attacks."),
        ],
        "F2-D §7.1",
    ),
    *_fields(
        "delta_v1",
        "PinRelation",
        GEOM,
        [
            ("pinner", "The pinning slider, by identity.", "rule"),
            ("pinned", "The pinned piece.", "rule"),
            ("king", "The king it is pinned to.", "rule"),
        ],
        "F2-D §7.1",
    ),
    *_fields(
        "delta_v1",
        "XRayRelation",
        GEOM,
        [
            ("slider", "The slider, by identity.", "rule"),
            ("first", "The piece x-rayed through.", "rule"),
            ("second", "The piece behind it.", "rule"),
        ],
        "F2-D §7.1",
    ),
    *_fields(
        "delta_v1",
        "BatteryRelation",
        GEOM,
        [("pieces", "The two sliders, by identity.")],
        "F2-D §7.1",
    ),
    *_fields(
        "delta_v1",
        "ZoneAttack",
        GEOM,
        [
            ("king", "The king, by identity.", "rule"),
            ("square", "The zone square."),
            ("attacker", "The attacking piece, by identity.", "rule"),
        ],
        "F2-D §7.1",
    ),
    *_fields(
        "delta_v1",
        "PieceFlags",
        "count",
        [
            ("attacked_without_defender", "Attacked and not defended (counts)."),
            ("attackers_exceed_defenders", "More attackers than defenders (counts)."),
        ],
        "F2-D §7.1",
    ),
    *_fields(
        "delta_v1",
        "PawnFlags",
        GEOM,
        [
            ("isolated", "As `PawnFacts.isolated`."),
            ("doubled", "As `PawnFacts.doubled`."),
            ("passed", "As `PawnFacts.passed`."),
            ("own_pawn_ahead", "As `PawnFacts.own_pawn_ahead`."),
            ("backward", "As `PawnFacts.backward`."),
        ],
        "F2-D §7.1",
    ),
    *_fields(
        "delta_v1",
        "FileChange",
        GEOM,
        [
            ("file", "The file.", "rule"),
            ("before", "Its `FileFacts` before."),
            ("after", "Its `FileFacts` after."),
        ],
        "F2-D §7.1",
    ),
    *_fields(
        "delta_v1",
        "IslandChange",
        GEOM,
        [
            ("color", "The colour.", "rule"),
            ("before", "Its islands before."),
            ("after", "Its islands after."),
        ],
        "F2-D §7.1",
    ),
    *_fields(
        "same_side_delta_v1",
        "SetDiff",
        "rule",
        [
            ("gained", "Members at the node and not at the grandparent."),
            ("lost", "Members at the grandparent and not at the node."),
        ],
        "F2-D §7.2",
    ),
    *_fields(
        "same_side_delta_v1",
        "SideMember",
        "rule",
        [
            ("piece", "The piece, by identity."),
            ("before", "Its type at the grandparent."),
            ("after", "Its type at the node, or `Absent`."),
        ],
        "F2-D §7.2",
    ),
    *_fields(
        "same_side_delta_v1",
        "DestinationChange",
        "rule",
        [
            ("piece", "The piece, by identity."),
            ("gained", "Legal destinations gained."),
            ("lost", "Legal destinations lost."),
        ],
        "F2-D §7.2",
    ),
    *_fields(
        "same_side_delta_v1",
        "CapturableChange",
        "rule",
        [
            ("piece", "The piece, by identity."),
            ("before", "Capturable at the grandparent."),
            ("after", "Capturable at the node."),
        ],
        "F2-D §7.2",
    ),
    *_fields("same_side_delta_v1", "PiecePair", "rule", PIECE_PAIR, "F2-D §7.2"),
    *_fields(
        "patterns_v1",
        "MultiTargetAttack",
        GEOM,
        [
            ("actor", "The attacking piece."),
            ("targets", "The enemy pieces it attacks, with their rank against it."),
        ],
        "F3-D §2",
        configuration_only=True,
    ),
    *_fields(
        "patterns_v1",
        "Target",
        GEOM,
        [
            ("piece", "The attacked piece."),
            ("order", "`Order`: above, equal or below the actor (`piece_order_v1`)."),
        ],
        "F3-D §2",
        configuration_only=True,
    ),
    _enum(
        "patterns_v1",
        "Order",
        "A target's rank against the actor under `piece_order_v1`: above, equal or below.",
        "F3-D §2",
    ),
    *_fields(
        "patterns_v1",
        "LinePattern",
        GEOM,
        [
            ("slider", "The slider."),
            ("line", "The ray's direction, from the slider outward."),
            ("front", "The nearer of the first two occupants."),
            ("back", "The farther."),
        ],
        "F3-D §2",
        configuration_only=True,
    ),
    *_fields(
        "patterns_v1",
        "SoleDefender",
        GEOM,
        [
            ("defender", "The only defender."),
            ("defended", "The two or more attacked pieces it alone defends."),
        ],
        "F3-D §2",
        configuration_only=True,
    ),
    *_fields(
        "patterns_v1",
        "BackRank",
        GEOM,
        [
            ("king", "The king on its first rank."),
            ("blockers", "Own pieces on its forward squares."),
            ("covered", "Forward squares not own-occupied and enemy-attacked."),
        ],
        "F3-D §2",
        configuration_only=True,
    ),
    *_fields("patterns_v1", "Relation", GEOM, RELATION, "F2-D §1.4"),
    *_fields(
        "pattern_delta_v1",
        "LineTriple",
        GEOM,
        [
            ("slider", "The slider, by identity."),
            ("front", "The nearer piece, by identity."),
            ("back", "The farther piece, by identity."),
        ],
        "F3-D §4",
        configuration_only=True,
    ),
    *_fields(
        "pattern_delta_v1",
        "TargetSetChange",
        GEOM,
        [
            ("piece", "The actor or defender, by identity."),
            ("before", "Its target or defended set before."),
            ("after", "The set after, or `Absent(CAPTURED)`."),
        ],
        "F3-D §4",
        configuration_only=True,
    ),
    *_fields(
        "pattern_delta_v1",
        "BackRankIds",
        GEOM,
        [
            ("blockers", "The blockers, by identity."),
            ("covered", "The covered squares."),
        ],
        "F3-D §4",
        configuration_only=True,
    ),
    *_fields(
        "pattern_delta_v1",
        "BackRankChange",
        GEOM,
        [
            ("king", "The king, by identity."),
            ("before", "Its back-rank configuration before, if any."),
            ("after", "After, if any."),
        ],
        "F3-D §4",
        configuration_only=True,
    ),
    *_fields(
        "pattern_delta_v1",
        "DefenceEnded",
        GEOM,
        [
            ("defender", "The defender, by identity."),
            ("defended", "The defended piece, still attacked."),
            ("reason", "`DefenceEndReason`."),
        ],
        "F3-D §4",
    ),
    _enum(
        "pattern_delta_v1",
        "DefenceEndReason",
        "Why a defence ended, first that applies: defender_captured, defender_moved (the mover or the castling rook), defended_moved, line_blocked.",
        "F3-D §4",
    ),
    *_fields("pattern_delta_v1", "SetChange", GEOM, SET_CHANGE, "F3-D §4"),
    *_fields(
        "exchange_v1",
        "ExchangeFacts",
        "rule",
        [("pieces", "Every non-king piece's `PieceExchange`, by square.")],
        "F6-D §2",
    ),
]

_TABLES = [
    Definition(
        "points_v1",
        "defined",
        "Material points: "
        + ", ".join(f"{t.value} {v}" for t, v in POINTS_V1_BY_TYPE.items())
        + "; the king has none. A counting convention.",
        "count",
        unit="points_v1",
        source="A0 §6.2",
    ),
    Definition(
        "piece_order_v1",
        "defined",
        "Piece rank for geometry: "
        + " > ".join(t.value for t, _ in sorted(PIECE_ORDER_RANK.items(), key=lambda kv: -kv[1]))
        + " (bishop and knight equal).",
        source="F2-D §1",
    ),
    Definition(
        "settle_v1",
        "defined",
        f"A path's material is settled when at least SETTLE_PLIES ({SETTLE_PLIES}) plies follow its last capture or promotion and the last ply is not a capture; a stalemate or automatic draw ends it drawn.",
        source="DF-D §5",
        depends_on=("SETTLE_PLIES",),
    ),
    Definition(
        "SETTLE_PLIES",
        "threshold",
        "Plies after the last material change for a path to be settled.",
        unit="plies",
        value=SETTLE_PLIES,
        source="DF-D §5",
    ),
]

_CLASSES = [
    Definition("RULE", "rule", "Follows from the rules of chess.", "rule", source="A0 §1"),
    Definition(
        "DEFINED", "defined", "Computed under a named, versioned definition.", source="A0 §1"
    ),
    Definition(
        "ATTESTED",
        "attested",
        "Reported by the engine, with its provenance (identity, profile, depth, MultiPV).",
        "engine",
        source="A0 §1",
    ),
]

_SENTINELS = [
    Definition(
        "NotObserved",
        "sentinel",
        "The value depends on the side to move and is undefined for this frame.",
        source="A0 §1",
    ),
    Definition(
        "HistoryUnknown",
        "sentinel",
        "The value depends on positions before the known history; an unproven negative.",
        source="A0 §2.2",
    ),
    Definition(
        "NotApplicable",
        "sentinel",
        "The value has no meaning here; its reason code says why.",
        source="A0 §1",
    ),
    Definition(
        "NotComputed",
        "sentinel",
        "The value was not computed; its reason code says why.",
        source="A0 §1",
    ),
    Definition(
        "Unavailable",
        "sentinel",
        "The engine does not provide the value (for instance no WDL).",
        source="A0 §1",
    ),
    Definition(
        "Absent",
        "sentinel",
        "The piece no longer exists in the role the fact describes: captured, or promoted.",
        source="F2-D §11",
    ),
]

_REASON_TEXT = {
    "IN_CHECK": "No `see_v1` for a piece of a side in check.",
    "NOT_EXPOSED": "Safe moves are listed only for an exposed piece (or a side in check).",
    "IRREGULAR_SEARCH": "The node's survey ended irregularly: no comparison basis.",
    "COMPARISON_NOT_REQUESTED": "The node's moves are not all in the survey and no comparison was asked for.",
    "PARENT_NOT_SEARCHED": "The parent node has no survey: no basis for its children.",
    "BUDGET": "The comparison was skipped for the session's search budget.",
    "DEADLINE": "The comparison was skipped for the request deadline.",
    "TIER": "An engine-only node holds only the tier families.",
    "NOT_REQUESTED": "An on-request family not yet ensured at this node.",
    "NO_SAME_SIDE_ANCESTOR": "No node of the same side to move two plies up (stored by `same_side_delta`).",
    "ROOT_HAS_NO_MOVE": "The root has no incoming move.",
    "TERMINAL": "The node ends the game, or follows a node that does.",
    "FAMILY_NOT_SELECTED": "The family is not in the session's families.",
    "NOT_COMPUTED_AT_NODE": "An eager family's record is missing at an input node.",
    "NOT_APPLICABLE_RECORD": "A record on a material path is not applicable (`material_flow`).",
}
assert set(_REASON_TEXT) == FACT_REASONS, "every fact reason code is stated"
_REASONS = [
    Definition(f"fact_reason.{c}", "reason", t, source="DF-D §6.2")
    for c, t in sorted(_REASON_TEXT.items())
]

DEFINITIONS: tuple[Definition, ...] = (
    *_FAMILIES, *_FIELD_ENTRIES, *_HELPERS, *_TABLES, *_CLASSES, *_SENTINELS, *_REASONS,
)  # fmt: skip


def as_json(definitions: tuple[Definition, ...]) -> list[dict]:
    """Entries as plain JSON, sorted by id (`definitions_v1`)."""

    return [
        {**asdict(d), "depends_on": list(d.depends_on)}
        for d in sorted(definitions, key=lambda d: d.id)
    ]


def digest(definitions: tuple[Definition, ...]) -> str:
    data = json.dumps(as_json(definitions), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def by_id(definitions: tuple[Definition, ...]) -> dict[str, Definition]:
    out: dict[str, Definition] = {}
    for d in definitions:
        if d.id in out:
            raise ValueError(f"two definitions are named {d.id}")
        out[d.id] = d
    return out


by_id(DEFINITIONS)  # ids are unique
