"""`agent_definitions_v1` (AG-D A9, §7): the agent's vocabulary, a registry of its own.

The proposition kinds and the uses of a claim (§4), the sentence classes and the token rules of
the sentence check (§5.3), piece identities (§3.7), the check's level, the prompts and the tool
set. Its digest is part of the agent build (§10), never of the reasoning build: the reasoning
registry (`definitions_v1`), every cache key and every job id stay as they are.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

FORMAT = "agent_definitions_v1"
TOOLS_VERSION = "agent_tools_v6"
# The guidance an agent reads (AG5-D §6): the server's instructions, the tool descriptions and what
# `definitions` finds. A change to any of them is a new version (tests pin it).
GUIDANCE_VERSION = "agent_guidance_v11"
KINDS = ("proposition", "use", "sentence_class", "token_rule", "identity", "check", "prompt",
         "tools", "budget", "board", "remark")  # fmt: skip


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    id: str
    kind: str
    statement: str
    fields: tuple[str, ...] = ()
    source: str = "AG-D"

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.id}: unknown kind {self.kind!r}")


def _p(name: str, fields: tuple[str, ...], rule: str) -> AgentDefinition:
    return AgentDefinition(f"proposition.{name}", "proposition", rule, fields, "AG-D §4")


PROPOSITIONS = (
    _p(
        "judgement",
        ("judgement", "move", "grade", "label", "best_move"),
        "Equal to the cited judgement (a j handle) of `ply` or `judge_move`; moves in SAN or "
        "UCI. A field left out is the judgement's (AG6-D §5.1): the handle alone is enough. A "
        "submission needs one on its subject's own judgement.",
    ),
    _p(
        "claim",
        ("claim", "use", "scopes"),
        "`claim` is a c handle. The use fits the claim (use.*). `scopes`, if given, equals the "
        "claim's effective_scopes as a set, every projected field of every scope, its own and "
        "its premises'; left out, they are the claim's (AG6-D §5.1).",
    ),
    _p(
        "engine_score",
        ("line", "move", "score", "depth"),
        "`line` is an s handle; the move, the score ({cp} or {mate}, White's view) and, if "
        "given, the depth equal the line's.",
    ),
    _p("engine_line", ("line", "moves"), "`line` is an s handle; its PV starts with `moves`."),
    _p(
        "material",
        ("line", "from", "to", "side", "balance"),
        "`line` is an x or s handle (an explored line, or a search line's PV); `material_flow` "
        "over the line's plies `from` to `to` (0 is its start) gives `balance(side, to - from)` "
        "in points_v1, the change since `from`; a missing record refuses.",
    ),
    _p(
        "attack",
        ("position", "attacker", "target"),
        "The target's square is in the attacker's `pieces.attacks.enemy`.",
    ),
    _p(
        "defence",
        ("position", "defender", "defended"),
        "The defender's square is in the defended piece's `pieces.defenders`.",
    ),
    _p(
        "exposed",
        ("position", "piece", "exposed", "gain"),
        "`exposed_v1` (exposed, not_exposed or undecided) and `exchange.gain` (points_v1 or "
        "IN_CHECK), computed in the facts tree; undecided verifies only as undecided.",
    ),
    _p(
        "pin",
        ("position", "pinned", "pinner"),
        "`pieces.absolutely_pinned.pinner` of the pinned piece.",
    ),
    _p("check", ("position", "checkers"), "`status.in_check` and `status.checkers`."),
    _p(
        "legal_moves",
        ("position", "moves", "count"),
        "`status.legal_moves` and `status.legal_move_count`.",
    ),
    _p(
        "pattern",
        ("position", "pattern", "participants"),
        "The configuration is in the `patterns_v1` record: actor/targets (multi-target attacks), "
        "slider/line/front/back (skewers, relative pins), defender/defended (sole defenders), "
        "king/blockers (back ranks). A configuration only.",
    ),
    _p(
        "pawn",
        ("position", "square", "flag", "value"),
        "The pawn on `square` has (value true) or has not (false) the `pawns_v1` flag `flag`: "
        "passed, isolated, doubled or backward (ST-D §4.3).",
    ),
    _p(
        "file",
        ("position", "file", "state"),
        "The file's pawn state in `pawns_v1`: open, semi_open_white (no white pawn), "
        "semi_open_black (no black pawn) or closed (ST-D §4.3).",
    ),
    _p(
        "after_reply",
        ("reply", "after_a", "after_b", "proposition_a", "proposition_b"),
        "after_a = P + a + r and after_b = P + b + r for one P; the two nested propositions, of one "
        "kind, verify at those positions: the same reply compared after two moves.",
    ),
    _p(
        "explored_line",
        ("line", "moves"),
        "`line` is an x handle and `moves` its moves: the session explored that line; the "
        "agent's plies are named as such (by: agent).",
    ),
    _p(
        "definition", ("definition",), "The entry exists in definitions_v1 or agent_definitions_v1."
    ),
)


def _u(name: str, rule: str) -> AgentDefinition:
    return AgentDefinition(f"use.{name}", "use", rule, (), "AG-D §4.1")


USES = (
    _u(
        "result",
        "SUPPORTED, a consequence; a claim of a catalogue/material template has its "
        "ATTRIBUTED check present and passed.",
    ),
    _u("line_fact", "SUPPORTED (any checks): what the line shows."),
    _u(
        "mechanism",
        "SUPPORTED with an explains or causes relation; a claim target must be "
        "SUPPORTED, a judgement or observation target is accepted.",
    ),
    _u("associated", "SUPPORTED with associated_with only: the configuration occurs."),
    _u("comparison", "A comparison claim, SUPPORTED."),
    _u("uncertain", "INCONCLUSIVE: could not be confirmed."),
    _u("not_the_case", "REFUTED."),
)

SENTENCES = (
    AgentDefinition(
        "sentence.sourced",
        "sentence_class",
        "States what its cited propositions say; its moves, scores, mates, squares "
        "and numbers must come from them. Not shown as verified: the propositions "
        "are.",
        (),
        "AG-D §5.3",
    ),
    AgentDefinition(
        "sentence.interpretation",
        "sentence_class",
        "The agent's reading, citing the propositions it rests on; stored and shown "
        "as interpretation.",
        (),
        "AG-D §5.3",
    ),
)

_TOKEN_RULES = {
    "split": (
        "The text is NFKC-normalised, characters shown as nothing are removed, and every dash and "
        "minus sign is read as `-` (AM2, AM4); tokens are maximal runs of [A-Za-z0-9.+\\-#=]; "
        "every other character separates. Across a gap with no letter or digit, `17.` or `17...` "
        "is joined with the next token, and a sign, `M` or `#` with the number after it (`- 1.00` "
        "reads as -1.00: a dash right before a number is its sign); a sign, `M` or `#` apart from "
        "the number after it (`- 약 1.00`, `Rxe3 — 백은 2점`) is a violation (AM5); before a word "
        "or a move it is no token. A trailing `.` is dropped (a lone move number reads as its "
        "integer). A digit of another script, or a letter or mark other than ASCII and Hangul "
        "touching a move or number, is a violation."
    ),
    "move": (
        "(\\d+(\\.|\\.\\.\\.) ?|\\.\\.\\.)?(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|"
        "[a-h]x[a-h][1-8](=[QRBN])?|[a-h][1-8]=[QRBN]|[a-h][1-8])[+#]?; a bare pawn push only "
        "with a move number or `...`; a move of a cited proposition, SAN at its "
        "position, the move number (when written) its fullmove number, `...` exactly for Black "
        "with or without a number (`.` only after one); `x` exactly for a capture, `+` only for "
        "a check that is not mate, `#` only for mate (AM2, AG7-D §5)."
    ),
    "score": (
        "[+\\-−]?\\d+\\.\\d{1,2}: round_half_away(cp_white / 100, d) of a cited engine_score; a "
        "negative score has a minus sign."
    ),
    "mate": "M\\d+ or #\\d+: |mate_white| of a cited engine_score.",
    "square": (
        "[a-h][1-8]: a square field of a cited proposition or the from or to square of a cited "
        "move."
    ),
    "integer": (
        "[+\\-−]?\\d+: an integer field of a cited proposition; a signed integer equals a signed "
        "field, an unsigned one may equal a field's absolute value."
    ),
    "violation": "Any other token containing a digit, e.g. 0-0, Stockfish16, 0.385, Ne9.",
}
TOKENS = tuple(
    AgentDefinition(f"token.{name}", "token_rule", rule, (), "AG-D §5.3 S3")
    for name, rule in _TOKEN_RULES.items()
)

OTHERS = (
    AgentDefinition(
        "piece_identity",
        "identity",
        "A piece by its colour, its type at the game's start and the square it "
        "stood on there (`origin`), with its current square and type (`type_now`, "
        "which differs for a promoted pawn).",
        ("piece", "type_now", "color", "origin", "square"),
        "AG-D §3.7",
    ),
    AgentDefinition(
        "commentary_check_v1",
        "check",
        "SOURCE_VERIFIED: every proposition verified against Calliope's data; every "
        "move, score, mate, square and number of a sentence from its cited "
        "propositions; interpretation marked. The wording is not verified.",
        (),
        "AG-D §5.3",
    ),
    AgentDefinition(
        "prompt.commentary_ko_v8",
        "prompt",
        "How to write the commentary (Korean): the scene's story in the commentator's own words, "
        "a fact about the board with its evidence; what each material is — `board_v4` (the scene "
        "before the move, since when an attack has stood, `structure`, `file`, `leads_to`, "
        "`held`, `opponent_first`, `played_material`), `others`, lines, claims; citing by handle, "
        "`as`, `proves` and `states`; a line's moves with their numbers; when 교환 is the word; "
        "how much to write. No type table, no notes.",
        (),
        "AG-D §6, AG8-D R8, MS-D R9, BL-D §6, PW-D §4, LM-D §3, ST-D §5",
    ),
    AgentDefinition(
        "prompt.check_ko_v1",
        "prompt",
        "How to check a commentary before submitting it (Korean).",
        (),
        "AG-D §6",
    ),
    AgentDefinition(
        TOOLS_VERSION,
        "tools",
        "open_game, ply, judge_move, facts, explore, definitions (AG1); "
        "submit_commentary and commentary (AG2); show_game, an MCP App (AG3b); detail, "
        "`view` on ply and judge_move, `items` on submit_commentary (AG6a); analyze_game, "
        "game_overview, show_game's calliope_view_v1 (AG6b); the proposition kinds pawn and file in "
        "submit_commentary (ST).",
        (),
        "AG-D §3",
    ),
    AgentDefinition(
        "budget.window_v1",
        "budget",
        "A local load limit of the server process over a rolling window of window_seconds: "
        "max_uncached_plies uncached analyses from any tool (at most "
        "max_uncached_plies_per_call in one call), max_searches engine calls metered at the "
        "engine port (store hits free, a retried attempt's calls charged); max_nodes_per_tree "
        "nodes in one game's facts tree. A refusal names retry_after_seconds when room comes "
        "back.",
        (
            "window_seconds",
            "max_uncached_plies",
            "max_uncached_plies_per_call",
            "max_searches",
            "max_nodes_per_tree",
        ),
        "AG-D §3.5, AG4-D §3",
    ),
    AgentDefinition(
        "budget.jobs_v1",
        "budget",
        "analyze_game's jobs, apart from budget.window_v1: at most max_job_plies plies in a job "
        "and max_queued_jobs queued beside the one that runs; max_job_plies_per_window uncached "
        "plies analysed by jobs per job_window_seconds (cache hits free). A job with no room "
        "waits and resumes by itself; its searches go to its own meter.",
        ("job_window_seconds", "max_job_plies", "max_job_plies_per_window", "max_queued_jobs"),
        "AG6-D §8",
    ),
)


def _b(name: str, fields: tuple[str, ...], rule: str) -> AgentDefinition:
    return AgentDefinition(f"board.{name}", "board", rule, fields, "AG8-D §2")


BOARD = (
    _b(
        "board_v4",
        ("v", "mover", "changes", "scene", "same_reply", "played_material", "refused"),
        "A digest's `board` (ply, judge_move): what the subject's move changed, by the mover's "
        "side, the scene the opponent's last move set, the same reply and, on a weak move, the "
        "played line's material — a view of the reasoning layer's piece relations at the move "
        "(MS-D §6, BL-D, ST-D). Every item: ref (a `b` handle), kind, part, proves, propositions "
        "(cite them as given, each with its own id); a change also owner and good_for; leads_to "
        "when a relation claim states its relation; opponent_first on a threat while the opponent "
        "can take a mover's piece first. On a weak move the changes other than threats come "
        "first, by what is at stake; `structure` and `file` items after the relation items.",
    ),
    _b(
        "held",
        ("owner", "good_for", "propositions", "leads_to"),
        "A mover's piece that could be won by exchange before the move and still can after it, "
        "from the facts (gain at least 3, or any gain on a weak move; not when the mover was in "
        "check before), or a piece a relation claim names: `exposed` and the `attack` of the "
        "piece that starts the exchange, before and after (MS-D §6 item 3, BL-D §2, §3). When one "
        "piece attacks it before and after, since when (ST-D §3).",
    ),
    _b(
        "scene",
        ("relation", "owner", "good_for", "propositions"),
        "What the opponent's previous move began against the mover's pieces — an attack, a double "
        "attack, a piece made capturable, a check, a pin — at the position before the move, and "
        "after the move whether each target is still attacked by that attacker (ST-D §2). At most "
        "three; none when a `held` item says the same piece.",
    ),
    _b(
        "since",
        (),
        "Since when an attack has stood (ST-D §3), appended to `lost_defence`, `held` and an "
        "exposed `weakness` or `threat`: since a move (its `attack` at that position), at least "
        "since a move (16 plies back), from the start; or, on `lost_defence`, new with the move. "
        "With it, the `attack` at the position before the move.",
    ),
    _b(
        "structure",
        ("owner", "good_for", "propositions"),
        "Pawns that became passed, isolated, doubled or backward with the move (`pawn` after, "
        "and before where the pawn was there): good for the owner when passed, else for the other "
        "side (ST-D §4.1).",
    ),
    _b(
        "file",
        ("owner", "good_for", "propositions"),
        "A file whose pawn state changed with the move (`file` before and after); good_for none "
        "(ST-D §4.2).",
    ),
    _b(
        "leads_to",
        ("claim", "template", "link", "to", "did"),
        "The relation claim that states the item's relation (the same kind, pieces, place and "
        "time): its handle, and its link to the consequence it explains, causes or only comes "
        "with; for a tactic, whether it won material (did: won) or was a configuration "
        "(MS-D §5, §6).",
    ),
    _b(
        "threat",
        ("owner", "good_for", "propositions"),
        "After the move, a check, a double attack of the mover's, an attack on a piece of the other "
        "side, a piece of the other side that can be won by exchange, or a pin of one, that was not "
        "there before (between the same pieces, by identity). The piece is the other side's; the "
        "mover does not lose it. An exposed one may say since when its attacker attacked it "
        "(board.since).",
    ),
    _b(
        "weakness",
        ("owner", "good_for", "propositions"),
        "After the move, a piece of the mover's that can be won by exchange, or is pinned, and was "
        "not before (the same piece, by identity, wherever it stood). An exposed piece comes with "
        "the `attack` of the piece that starts the exchange (BL-D §3), and since when that piece "
        "attacked it, if before the move (board.since).",
    ),
    _b(
        "lost_defence",
        ("owner", "good_for", "propositions"),
        "A piece of the mover's that had a defender before the move and has not after, and that a "
        "piece of the other side attacks after: `defence` (before) and `attack` (after). Read "
        "from pattern_delta's defences_ended_under_attack by piece identity: the defender moved "
        "or the move blocked its line. Since when the attack stood, or that it is new (board.since).",
    ),
    _b(
        "same_reply",
        ("propositions",),
        "For a move that is not the best: the played line's reply played after the best move; the "
        "mover's next move kept only when the engine plays it there too; an explored_line by "
        "calliope, the engine's score at its end and the played line's score. Or not_computed "
        "(budget, engine_busy, reply_illegal, game_over, refused).",
    ),
    _b(
        "played_material",
        ("owner", "good_for", "propositions"),
        "On a weak move whose material_loss_v2 is INCONCLUSIVE (not MATE_LINE): the mover's "
        "balance (its points minus the other side's) at two plies of the played line as the "
        "digest shows it (8 plies), when it ends behind and not on a capture and the best line "
        "ends better; two `material` propositions, part consequence. Not the line's outcome nor a "
        "comparison; not the reasoning layer's observation line_material (BL-D §4).",
    ),
    _b(
        "opponent_first",
        (),
        "On a weak move's threat (not a check), the side to move not in check: the ref of the "
        "mover's exposed item of gain at least 3 (the largest) the opponent can take before the "
        "threat matters (BL-D §5).",
    ),
    AgentDefinition(
        "board_remarks_ko_v5",
        "board",
        "The Korean templates of `proves`: a bracket naming the mover and whose the "
        "item is, then the pieces by colour, type and square; one for every template, saying "
        "what it verifies and no more, its moves, squares and numbers allowed in a sentence "
        "citing it (MS-D §8.2, §8.3). Moves numbered as in PGN; an exposed piece's cost said "
        "from its owner's side, as one square's capture count, without 교환 (PW-D §3). The scene, "
        "since when, pawn structure and files (ST-D §2–§4); an appended part whole or not at all.",
        (),
        "AG8-D §3; MS-D §8; BL-D §3–§5; PW-D §2–§3; ST-D §2–§4, §7",
    ),
)
REMARKS = (
    AgentDefinition(
        "remark.part",
        "remark",
        "The part a remark plays: reason (why the move is good or bad), consequence "
        "(what it leads to), comparison (that another move is better), grade (the "
        "judgement), line (an engine line or score), other.",
        (),
        "AG8-D §3",
    ),
    AgentDefinition(
        "remark.proves",
        "remark",
        "What a board item or a consequence claim proves, in Korean; saying more is a reading.",
        (),
        "AG8-D §3, §4",
    ),
    AgentDefinition(
        "remark.en_passant",
        "remark",
        "A digest's en passant captures in its lines, in Korean: the SAN names the empty square "
        "the pawn goes to, the text the pawn it takes.",
        (),
        "AG8 implementation §2",
    ),
    AgentDefinition(
        "sentence.states",
        "sentence_class",
        "Optional: the cited propositions a sentence says (S7). A board item is stated "
        "when all its propositions are.",
        (),
        "AG8-D §6",
    ),
    AgentDefinition(
        "commentary_check_v6",
        "check",
        "commentary_check_v1 and S7 (a stated proposition that allows a token has one "
        "written), S8 (a ko sentence contains Hangul and no kana or CJK ideograph); a handle in "
        "`cites` or `states` stands for the propositions the server builds for it, checked as "
        "given (MS-D §9). No notes: v5's N-reason and N-reading are off (ST-D §6).",
        (),
        "AG8-D §6, MS-D §9, CV4-D, BL-D §6, ST-D §6",
    ),
    AgentDefinition(
        "cite.handle",
        "check",
        "A sentence may cite a handle this game served (j a judgement, c a claim, s an "
        "engine line, b a board item, x an explored line): it stands for the propositions the "
        "server builds for it, each with its own id `<handle>:<part>` (judgement, claim, score "
        "and line, 0…n, line); a line without a PV gives its score alone. An agent's id has no "
        "colon. f (a fact record) is not cited by itself.",
        (),
        "MS-D §9.1",
    ),
    AgentDefinition(
        "use.by_server",
        "check",
        "A claim cited by handle, or a claim proposition without `use`, is stored with the "
        "first use `_use` allows, in the order result, mechanism, associated, comparison, "
        "line_fact, uncertain, not_the_case, and `use_by: server`; the digest shows it as "
        "`as`. An explicit `use` is checked as before.",
        (),
        "MS-D §9.2",
    ),
    AgentDefinition(
        "claim.as",
        "remark",
        "The use a listed claim is stored with when cited without one (use.by_server).",
        (),
        "MS-D §9.2",
    ),
    AgentDefinition(
        "claim.group",
        "remark",
        "Claims that say one thing with different evidence (a better move; the move offers "
        "material; the move allows a mate) are shown once: the first SUPPORTED member by what "
        "it names, else the first INCONCLUSIVE; the others in `also` with their status.",
        (),
        "MS-D §7",
    ),
    AgentDefinition(
        "piece_relations_v2",
        "remark",
        "A relation between pieces, by piece identity: kind (attack, defence, exposed, check, "
        "double_attack, absolute_pin, relative_pin, skewer, discovered_attack), its pieces in the "
        "kind's roles, its place, its time, the side it bears on and its data (gain; defenders "
        "and attackers after a lost defence). At a move the mover's pieces exposed before and "
        "after are `held` (not when the mover was in check before).",
        (),
        "MS-D §4.1, BL-D §2",
    ),
    AgentDefinition(
        "relation.time",
        "remark",
        "When a relation stands against the move: began (after it, not before), held (before "
        "and after), ended (before it, not after); a line's relation is began at its ply.",
        (),
        "MS-D §4.1",
    ),
    AgentDefinition(
        "relation.place",
        "remark",
        "Where a relation stands: at the move (`at: move`), or at ply k of an engine line "
        "(`at: line`, `ply` from 1, the line's `search` and `rank`). A line's relation is said "
        "of that line, never of the move.",
        (),
        "MS-D §4.1",
    ),
    AgentDefinition(
        "claim.link",
        "remark",
        "How a relation claim stands to the consequence it is read with: explains or causes (the "
        "relation leads to it), associated_with (it only comes with it); for a tactic, did: won "
        "(it won material) or configuration (a configuration only).",
        (),
        "MS-D §5",
    ),
    AgentDefinition(
        "mate_over_scores",
        "remark",
        "sacrifice_compensated_v2's finding when the offer's line ends in mate and a keeping "
        "line's material is open: that line is compared by its engine score (no mate for the "
        "mover), an evaluation, not its decided outcome.",
        (),
        "MS-D §3",
    ),
)

AGENT_DEFINITIONS: tuple[AgentDefinition, ...] = (
    *PROPOSITIONS, *USES, *SENTENCES, *TOKENS, *OTHERS, *BOARD, *REMARKS,
)  # fmt: skip
assert len({d.id for d in AGENT_DEFINITIONS}) == len(AGENT_DEFINITIONS), "ids are unique"


def as_json(definitions=AGENT_DEFINITIONS) -> list[dict]:
    return [
        {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(d).items()}
        for d in sorted(definitions, key=lambda d: d.id)
    ]


def _digest(definitions) -> str:
    text = json.dumps(as_json(definitions), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)  # fmt: skip
    return hashlib.sha256(text.encode()).hexdigest()


AGENT_DIGEST = _digest(AGENT_DEFINITIONS)


def document() -> dict:
    return {"format": FORMAT, "digest": AGENT_DIGEST, "definitions": as_json()}
