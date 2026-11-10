"""HS-D: arm H of the RX runner — per fixed moment, the facts and the decisive cause in one turn, a
judge that never sees the key causes, at most two retries, then the submit step behind a gate.

LT-D §5 (rev. 5, the default): the facts reply ends with a block of typed claims; code checks each
claim's value and source against the record its handle serves (H2, never the prose); the judge reads
the checked claims and their records (rubric v3, H3); at submission a model request reads the final
sentences against the checked claims and holds a contradicting or unbacked one (H5). Rev. 4 (HS rev.
4, `harness_v2`) stays reachable for its runs (`RunSpec.harness_revision`).

The stages drive `run._loop` (the plain loop) with the runner's messages from `harness_v1.md`; the
judge is one request on the run's model with `harness_judge_v1.md`. The gate (`(phase, current_ply)`,
review B2) sends `submit_commentary` to the server only at the current moment's submit step and only
when every subject of the call is that moment; anything else is answered by the runner and logged as
`tool_unsent` with `reason: "harness_gate"`.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from types import SimpleNamespace

import anyio
import chess.pgn

PROMPTS = Path(__file__).resolve().parent / "prompts"
REVISION = 8  # AF-D §4: rev. 7's stages with the code frame check in place of the sentence check
# revision → (messages, judge rubric, sentence check)
VERSIONS = {
    4: ("harness_v2", "harness_judge_v1", None),
    5: ("harness_v3", "harness_judge_v2", "harness_sentences_v1"),
    6: ("harness_v3", "harness_judge_v2", "harness_sentences_v2"),  # scores by side, not digits
    7: ("harness_v3", "harness_judge_v3", "harness_sentences_v2"),  # the judge reads scores so too
    8: ("harness_v4", "harness_judge_v3", None),  # AF-D §4: the frame check, no model check
    9: ("harness_v5", "harness_judge_v3", None),  # TB-D §3: a conversation per moment, the guard
    10: ("harness_v5", "harness_judge_v3", None),  # rev. 9 with the frame check v2 (change log)
    11: ("harness_v5", "harness_judge_v3", None),  # rev. 10 with the frame check v3 (change log)
    12: ("harness_v6", "harness_judge_v3", None),  # WG-D: rev. 11 and tier 1's batches, tier 0
    13: ("harness_v6", "harness_judge_v3", None),  # rev. 12, tier 1 cheaper (the change log)
    14: ("harness_v6", "harness_judge_v3", None),  # rev. 13, short handles resolved (change log)
    15: ("harness_v6", "harness_judge_v3", None),  # rev. 14, tier-1 cites completed (change log)
}
# AF-D §4.4: the frame check (code); v2 holds a change written with "물질 차이"/"물질은" too;
# v3 reads the cited line's ledger, crossovers, "no change" and ledger terms
# v4 (rev. 12): v3 without the false holds the review of 2026-11-10 found
FRAMES = {8: "harness_frames_v1", 9: "harness_frames_v1", 10: "harness_frames_v2",
          11: "harness_frames_v3", 12: "harness_frames_v4",
          13: "harness_frames_v4", 14: "harness_frames_v4", 15: "harness_frames_v4"}  # fmt: skip
# TB-D B1: the revisions with a conversation per moment and the guard
PER_MOMENT = (9, 10, 11, 12, 13, 14, 15)
# TB-D B2: the tools a rev. 9 harness serves, and its system message
HARNESS_TOOLS = ("ply", "judge_move", "detail", "facts", "explore", "compare_lines", "squares",
                 "game_overview", "submit_commentary", "definitions")  # fmt: skip
TIERED = (12, 13, 14, 15)  # WG-D: the revisions that comment the whole game in three tiers
TIER1_GUIDE = "harness_tier1_v1"  # WG-D §2.1: tier 1's system message (rev. 12)
TIER1_GUIDES = {12: TIER1_GUIDE, 13: "harness_tier1_v2", 14: "harness_tier1_v2",
                15: "harness_tier1_v3"}  # v2: no handle in a sentence's text; v3: what a number cites  # fmt: skip
# rev. 13 (the change log, "tier 1 cheaper"): handles written into a tier-1 sentence's text are
# taken out before the call is sent, and a batch ends once every ply of it is accepted
LEAN_TIER1 = (13, 14, 15)
# rev. 14: a tier-1 cite written by its short name ("j7" for "j7.<24 hex>") is the handle of that
# name in its ply's digest, when the digest has exactly one
SHORT_HANDLES = (14, 15)
# rev. 15: a tier-1 sentence that writes a score or a rank ("1순위") its ply's digest gives under a
# handle the sentence does not cite has that handle added to its `cites`
COMPLETE_CITES = (15,)
TIER1_TOOLS = ("detail", "submit_commentary")  # WG-D §2: no explore, facts or ply
TIER1_FIRST = 60_000  # WG-D §2: a batch's first message, counted tokens at most
TIER1_TURNS = 6  # WG-D §2: a batch's turns at most
TIER1_ASKS = 2  # re-asks when a batch ends with nothing accepted
HARNESS_GUIDE = "harness_guide_v1"  # TB-D B2: v2 (9,019 tokens) had twice v1's wrong sentences
ANSWER_CAP = 24_576  # TB-D B3: a tool message's `content`, UTF-8 bytes
MOMENT_ENDS = (
    "moment_budget",
    "moment_cut",
    "moment_refused",
)  # TB-D B7: the moment ends, not the run
# the sentence-check verdicts that hold a submission, by revision (A12: from 7, contradictions only;
# `unbacked` sentences are recorded, not held)
HOLD_ON = {5: ("contradicts", "unbacked"), 6: ("contradicts", "unbacked"), 7: ("contradicts",)}
HARNESS_VERSION, JUDGE_VERSION, SENTENCES_VERSION = VERSIONS[REVISION]
RETRIES = 2
SUBMIT_ASKS = 3  # HS rev. 4 (A2): re-asks when a submit step ends with its moment not accepted
HOLDS = 2  # LT-D §5.5: holds of the sentence check a moment; the next call goes unchecked
JUDGE_RECORDS = 2500  # LT-D §5.3: characters of the cited records' summaries the judge reads
CLAIM_KINDS = ("line_net", "line_capture", "piece_at_end", "defenders", "attackers",
               "better_for_mover", "score")  # fmt: skip


def messages_of(path: Path = PROMPTS / f"{HARNESS_VERSION}.md") -> dict[str, str]:
    """The `## name` sections of `harness_v1.md`, each its text."""

    out, name, lines = {}, None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if name:
                out[name] = "\n".join(lines).strip()
            name, lines = line[3:].strip(), []
        elif name:
            lines.append(line)
    if name:
        out[name] = "\n".join(lines).strip()
    return out


def _system(name: str | None) -> str | None:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip() if name else None


ALL_MESSAGES = {rev: messages_of(PROMPTS / f"{v[0]}.md") for rev, v in VERSIONS.items()}
JUDGES = {rev: _system(v[1]) for rev, v in VERSIONS.items()}
SENTENCE_SYSTEMS = {rev: _system(v[2]) for rev, v in VERSIONS.items()}
MESSAGES = ALL_MESSAGES[REVISION]
JUDGE_SYSTEM = JUDGES[REVISION]


def revision_of(spec) -> int:
    """The harness revision a run uses: `RunSpec.harness_revision`, rev. 5 by default."""

    rev = getattr(spec, "harness_revision", REVISION)
    if rev not in VERSIONS:
        raise ValueError(f"no harness revision {rev}; revisions: {sorted(VERSIONS)}")
    return rev


class Game:
    """The game's moves, for the gate's check of a subject named by position and move."""

    def __init__(self, pgn: str) -> None:
        game = chess.pgn.read_game(io.StringIO(pgn))
        board = game.board()
        self.uci, self.san = [], []
        for move in game.mainline_moves():
            self.uci.append(move.uci())
            self.san.append(board.san(move))
            board.push(move)

    def before(self, ply: int) -> list[str]:
        return self.uci[: ply - 1]


def _position_path(position, game: Game) -> list[str] | None:
    if not isinstance(position, dict):
        return None
    if isinstance(position.get("from_root"), list):
        return [str(m) for m in position["from_root"]]
    ply, at = position.get("ply"), position.get("at", "after")
    if isinstance(ply, int) and not isinstance(ply, bool):
        return game.uci[: ply if at == "after" else ply - 1]
    return None


def subject_ply(subject, game: Game) -> int | None:
    """The game ply a subject of `submit_commentary` names, or None (a variation, a malformed
    subject). By `ply`, or by `position` and `move` when the position is the one before a played
    move and the move is that move (in UCI or SAN)."""

    if not isinstance(subject, dict):
        return None
    ply = subject.get("ply")
    if ply is not None:
        return ply if isinstance(ply, int) and not isinstance(ply, bool) else None
    path, move = _position_path(subject.get("position"), game), subject.get("move")
    if path is None or not isinstance(move, str):
        return None
    candidate = len(path) + 1
    if candidate > len(game.uci) or path != game.before(candidate):
        return None
    return candidate if move in (game.uci[candidate - 1], game.san[candidate - 1]) else None


def _json(value):
    """A JSON string read as its value, as the MCP server reads an argument given as a string for a
    list or an object (`pre_parse_json`, HS rev. 4 A3); anything else as it is."""

    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def normalized(arguments: dict) -> dict:
    """A `submit_commentary` call's arguments with `items`, `position` and each item's `position`
    read as the server reads them (A3)."""

    out = dict(arguments)
    for key in ("items", "position"):
        if key in out:
            out[key] = _json(out[key])
    if isinstance(out.get("items"), list):
        out["items"] = [
            (
                {**i, "position": _json(i["position"])}
                if isinstance(i, dict) and "position" in i
                else i
            )
            for i in out["items"]
        ]
    return out


def accepted(text: str) -> bool:
    """Whether a `submit_commentary` answer accepted its subject, or one of its items (the gate let
    only the current moment through): `accepted`, or an item `accepted` or `duplicate`."""

    try:
        answer = json.loads(text)
    except ValueError:
        return False
    if not isinstance(answer, dict):
        return False
    if isinstance(answer.get("items"), list):
        return any(
            isinstance(o, dict) and o.get("outcome") in ("accepted", "duplicate")
            for o in answer["items"]
        )
    return answer.get("accepted") is True


def accepted_subjects(arguments: dict, text: str, game: Game,
                      current: int | None) -> list[tuple[int, list[str], list[str]]]:  # fmt: skip
    """WG-D §2: each subject a `submit_commentary` answer accepted (or found a duplicate of), as
    (its ply, its sentences, the handles they cite); a call without `items` is the current ply's."""

    try:
        answer = json.loads(text)
    except ValueError:
        return []
    if not isinstance(answer, dict):
        return []

    def parts(subject) -> tuple[list[str], list[str]]:
        sentences = [s for s in (subject or {}).get("sentences") or [] if isinstance(s, dict)]
        texts = [s["text"] for s in sentences if isinstance(s.get("text"), str) and s["text"]]
        cites = [c for s in sentences for c in s.get("cites") or [] if isinstance(c, str)]
        return texts, list(dict.fromkeys(cites))

    if isinstance(answer.get("items"), list):
        items = arguments.get("items") if isinstance(arguments.get("items"), list) else []
        out = []
        for position, outcome in enumerate(answer["items"]):
            if not isinstance(outcome, dict) or outcome.get("outcome") not in ("accepted", "duplicate"):
                continue
            index = outcome.get("index", position)
            subject = items[index] if isinstance(index, int) and 0 <= index < len(items) else None
            ply = subject_ply(subject, game) if isinstance(subject, dict) else None
            if ply is not None:
                out.append((ply, *parts(subject)))
        return out
    if answer.get("accepted") is True:
        ply = current if current is not None else subject_ply(arguments, game)
        return [(ply, *parts(arguments))] if ply is not None else []
    return []


HANDLE_NOTE = re.compile(r"\s*[(\[]\s*([A-Za-z][\w.:-]*(?:\s*[,/·]\s*[A-Za-z][\w.:-]*)*)\s*[)\]]")


def strip_cited_handles(arguments: dict) -> tuple[dict, int]:
    """Rev. 13: a bracket in a sentence's text that holds only handles the sentence cites ("(j11)",
    "(c47, s111)", the full ref or its short name) is taken out; anything else stays. The
    arguments as sent, and how many brackets went."""

    out = json.loads(json.dumps(arguments))
    removed = 0
    subjects = out["items"] if isinstance(out.get("items"), list) else [out]
    for subject in subjects:
        if not isinstance(subject, dict):
            continue
        for sentence in subject.get("sentences") or []:
            if not isinstance(sentence, dict) or not isinstance(sentence.get("text"), str):
                continue
            cites = [c for c in sentence.get("cites") or [] if isinstance(c, str)]
            names = set(cites) | {c.split(".", 1)[0] for c in cites} | {c.split(":", 1)[0] for c in cites}

            def drop(match, names=names):
                nonlocal removed
                tokens = [t.strip() for t in re.split(r"[,/·]", match.group(1))]
                if tokens and all(t in names for t in tokens):
                    removed += 1
                    return ""
                return match.group(0)

            sentence["text"] = HANDLE_NOTE.sub(drop, sentence["text"])
    return out, removed


def short_names(text: str) -> dict[str, str]:
    """Rev. 14: each handle an answer writes, by its short name ("j7"); a name two handles share
    is left out."""

    from calliope.agent.record import HANDLE

    seen: dict[str, set[str]] = {}
    for ref in HANDLE.findall(text or ""):
        seen.setdefault(ref.split(".", 1)[0], set()).add(ref)
    return {name: next(iter(refs)) for name, refs in seen.items() if len(refs) == 1}


def resolve_short_handles(arguments: dict, refs: dict[int, dict[str, str]],
                          game: Game) -> tuple[dict, int]:  # fmt: skip
    """Rev. 14: each subject's `cites` and `states` written by a short name its ply's digest has,
    as the full handle. The arguments as sent, and how many were resolved."""

    out = json.loads(json.dumps(arguments))
    resolved = 0
    subjects = out["items"] if isinstance(out.get("items"), list) else [out]
    for subject in subjects:
        if not isinstance(subject, dict):
            continue
        ply = subject_ply(subject, game)
        names = refs.get(ply) or {}
        ids = {p.get("id") for p in subject.get("propositions") or [] if isinstance(p, dict)}
        for sentence in subject.get("sentences") or []:
            if not isinstance(sentence, dict):
                continue
            for field in ("cites", "states"):
                values = sentence.get(field)
                if not isinstance(values, list):
                    continue
                new = []
                for value in values:
                    if isinstance(value, str) and value not in ids and value in names:
                        new.append(names[value])
                        resolved += 1
                    else:
                        new.append(value)
                sentence[field] = new
    return out, resolved


RANK = re.compile(r"(\d+)\s*순위")
_SCORE_TOKEN = re.compile(r"[+\-]?\d+\.\d{1,2}")


def _score_key(text: str) -> str:
    return text.replace("\u2212", "-").removeprefix("+")


def digest_sources(text: str) -> dict:
    """Rev. 15: from a `ply` answer, the handles that give each score ("+6.99") and each rank
    ("1순위" in a claim's `proves`). Scores: the played and best lines' handles first, then any
    other line's; ranks: claims shown as supported (or with no status)."""

    try:
        data = json.loads(text or "")
    except ValueError:
        return {"scores": {}, "ranks": {}}
    lines = data.get("lines") if isinstance(data, dict) else None
    main = {v["ref"] for v in (lines or {}).values()
            if isinstance(v, dict) and isinstance(v.get("ref"), str)}  # fmt: skip
    scores: dict[str, list[str]] = {}
    ranks: dict[int, list[str]] = {}

    def walk(value) -> None:
        if isinstance(value, dict):
            ref = value.get("ref")
            if isinstance(ref, str):
                if isinstance(value.get("score_text"), str):
                    scores.setdefault(_score_key(value["score_text"]), []).append(ref)
                if isinstance(value.get("proves"), str) and value.get("status") in (None, "supported"):
                    for n in RANK.findall(value["proves"]):
                        ranks.setdefault(int(n), []).append(ref)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(data)
    order = {k: sorted(set(v), key=lambda r: (r not in main, r)) for k, v in scores.items()}
    return {"scores": order, "ranks": {k: sorted(set(v)) for k, v in ranks.items()}}


def complete_cites(arguments: dict, sources: dict[int, dict],
                   game: Game) -> tuple[dict, list[str]]:  # fmt: skip
    """Rev. 15: a sentence that writes a score or a rank its ply's digest gives, under no handle
    the sentence cites, cites the first such handle too. The arguments as sent, and the handles
    added."""

    from calliope.agent.sentences import tokens

    out = json.loads(json.dumps(arguments))
    added: list[str] = []
    subjects = out["items"] if isinstance(out.get("items"), list) else [out]
    for subject in subjects:
        if not isinstance(subject, dict):
            continue
        source = sources.get(subject_ply(subject, game))
        if not source:
            continue
        for sentence in subject.get("sentences") or []:
            if not isinstance(sentence, dict) or not isinstance(sentence.get("text"), str):
                continue
            cites = sentence.get("cites")
            if not isinstance(cites, list):
                continue
            wanted = [source["scores"].get(_score_key(t)) or []
                      for t in tokens(sentence["text"]) if _SCORE_TOKEN.fullmatch(t)]  # fmt: skip
            wanted += [source["ranks"].get(int(n)) or [] for n in RANK.findall(sentence["text"])]
            for refs in wanted:
                if refs and not any(r in cites for r in refs):
                    cites.append(refs[0])
                    added.append(refs[0])
    return out, added


def subjects_of(arguments: dict) -> list:
    """Every subject of a `submit_commentary` call: its `items`, or the call itself."""

    if "items" in arguments:
        items = arguments.get("items")
        return list(items) if isinstance(items, list) else [None]
    return [arguments]


# -- LT-D §5.1–5.2: typed claims and the checker ----------------------------------------------


def claims_of(reply: str) -> list | None:
    """The claims block of a facts reply (H1): the last JSON object holding `claims`, fenced or
    not; None when there is none or it is not a list."""

    candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", reply or "", re.DOTALL)
    start = (reply or "").rfind('{"claims"')
    if start >= 0:
        candidates.append(reply[start:])
    for text in reversed(candidates):
        for end in range(len(text), 0, -1):
            if text[end - 1] != "}":
                continue
            try:
                block = json.loads(text[:end])
            except ValueError:
                continue
            if isinstance(block, dict) and isinstance(block.get("claims"), list):
                return block["claims"]
            break
    return None


def _strip_move(text) -> str:
    text = re.sub(r"^\d+\.(\.\.)?", "", str(text or "").strip())
    return text.rstrip("+#!?")


def _names(values) -> set[str]:
    """Pieces by name, case aside: the role (attacker, defender) fixes the colour, and an agent may
    write a black king `Kg8` as the guide's notation does."""

    return {str(v).split()[0].lower() for v in values or []}


def check_claim(claim: dict, kind: str | None, item) -> tuple[str, object]:
    """One claim against the record its handle serves (H2): `agrees`, `disagrees` with the
    record's value, or `unbacked` (the record holds no such value). Never the prose."""

    from calliope.agent.lines import favours, ledger, rank_key, square_entry

    what = claim.get("kind")
    try:
        if what in ("line_net", "line_capture", "piece_at_end"):
            if kind != "explored_line" or not isinstance(item, dict):
                return "unbacked", f"{claim.get('ref')} is not an explored line"
            book = item.get("ledger") or ledger(item.get("plies") or [], item["start"]["fen"])
            if what == "line_net":
                held = book["net"].get(claim.get("side"))
                return ("agrees" if held == claim.get("value") else "disagrees"), held
            if what == "line_capture":
                taken = [(p["side"], (p.get("captured") or {}).get("piece"),
                          (p.get("captured") or {}).get("square"))
                         for p in book["plies"] if p.get("captured")]  # fmt: skip
                want = (claim.get("by"), claim.get("piece"), claim.get("square"))
                return ("agrees" if want in taken else "disagrees"), taken
            board = chess.Board(item["end"]["fen"])
            piece = board.piece_at(chess.parse_square(str(claim.get("square"))))
            held = (
                None
                if piece is None
                else ("white" if piece.color else "black", chess.piece_name(piece.piece_type))
            )
            want = (claim.get("side"), claim.get("piece"))
            return ("agrees" if held == want else "disagrees"), held
        if what in ("defenders", "attackers"):
            pieces = (item or {}).get("pieces") if isinstance(item, dict) else None
            if kind != "fact" or not isinstance(pieces, list):
                return "unbacked", f"{claim.get('ref')} is not a pieces record"
            entry = square_entry(str(claim.get("square")), pieces, None)
            role = entry.get(what)
            if role is None:  # an empty square has attackers only
                return "unbacked", f"{claim.get('square')} is empty: it has no {what}"
            if isinstance(role, dict):
                side = claim.get("side")
                role = role.get(side, []) if side else role["white"] + role["black"]
            held = sorted(_names(x["piece"] for x in role))
            return ("agrees" if set(held) == _names(claim.get("value")) else "disagrees"), held
        if what == "better_for_mover":
            table = (item or {}).get("ranking") if isinstance(item, dict) else None
            moves = (table or {}).get("moves")
            if kind != "comparison" or not isinstance(moves, list):
                return "unbacked", f"{claim.get('ref')} is not a ranking"
            # LT review F3: the scores, not the places: a tie is not "better"
            score = {_strip_move(m.get("move")): m.get("for_mover") for m in moves}
            a = score.get(_strip_move(claim.get("move")))
            b = score.get(_strip_move(claim.get("than")))
            ka, kb = rank_key(a, table.get("for")), rank_key(b, table.get("for"))
            if ka is None or kb is None:  # unranked, or not in the ranking
                return "unbacked", {"ranked": list(score)}
            return ("agrees" if ka > kb else "disagrees"), {"for_mover": [a, b]}
        if what == "score":
            if kind != "search_line" or not isinstance(item, dict):
                return "unbacked", f"{claim.get('ref')} is not an engine line"
            held = favours(item.get("score"))
            return ("agrees" if held == claim.get("favours") else "disagrees"), held
    except (KeyError, TypeError, ValueError) as error:
        return "unbacked", f"the record cannot answer it: {error}"
    return "unbacked", f"no claim kind {what!r}; kinds: {', '.join(CLAIM_KINDS)}"


def _summary(kind: str | None, item, claim: dict) -> object:
    """What the judge reads of a cited record (H3): a ledger outcome, a square entry, a ranking, a
    score."""

    from calliope.agent.lines import ledger, outcome, square_entry

    if not isinstance(item, dict):
        return None
    if kind == "explored_line":
        book = item.get("ledger") or ledger(item.get("plies") or [], item["start"]["fen"])
        return {"moves": [p["san"] for p in book["plies"]], **outcome(book)}
    if kind == "fact" and isinstance(item.get("pieces"), list):
        return square_entry(str(claim.get("square")), item["pieces"], None)
    if kind == "comparison":
        return [{k: m.get(k) for k in ("move", "rank", "for_mover", "vs_played")}
                for m in (item.get("ranking") or {}).get("moves") or []]  # fmt: skip
    if kind == "search_line":
        return {"score": item.get("score"), "move": (item.get("move") or {}).get("san")}
    return None


async def read_record(session, game_id: str, ref, log,
                      before: str | None = None) -> tuple[str | None, object]:  # fmt: skip
    """A record through the server's `detail`, as the harness's own call (`harness_call`, review
    F3): logged so the run checker pairs it with the server's line; never shown to the agent."""

    if not isinstance(ref, str):
        return None, None
    line = {"type": "harness_call", "tool": "detail", "ref": ref}
    if before is not None:  # made while the model's call `before` waits: the server has it first
        line["before"] = before
    log.write(line)
    result = await session.call_tool("detail", {"game": game_id, "ref": ref})
    text = "\n".join(getattr(c, "text", "") for c in (result.content or [])
                     if getattr(c, "type", None) == "text")  # fmt: skip
    if getattr(result, "isError", False):
        return None, None
    try:
        answer = json.loads(text)
    except ValueError:
        return None, None
    return answer.get("kind"), answer.get("item")


async def check_claims(session, game_id: str, claims, log) -> tuple[list, list, list]:
    """H2: every claim checked; (results, problems, the agreeing claims with their records)."""

    if not isinstance(claims, list) or not claims:
        return [], [MESSAGES_NO_CLAIMS], []
    results, problems, checked = [], [], []
    for i, claim in enumerate(claims, start=1):
        claim = claim if isinstance(claim, dict) else {"kind": None}
        kind, item = await read_record(session, game_id, claim.get("ref"), log)
        if kind is None:
            verdict, held = "unbacked", f"no record {claim.get('ref')!r}"
        else:
            verdict, held = check_claim(claim, kind, item)
        results.append({"n": i, "claim": claim, "result": verdict, "record": held})
        if verdict == "agrees":
            checked.append({"n": i, "claim": claim, "record": _summary(kind, item, claim)})
        else:
            problems.append(f"주장 {i} ({claim.get('kind')}): "
                            + (f"기록 {claim.get('ref')}의 값은 {json.dumps(held, ensure_ascii=False)}"
                               if verdict == "disagrees" else f"기록이 뒷받침하지 않음 — {held}"))  # fmt: skip
    return results, problems, checked


MESSAGES_NO_CLAIMS = "주장 블록이 없거나 JSON이 아님: 원인의 주장을 기록의 ref와 함께 블록으로 적어"


def judge_input(move: str, reply: str, checked: list) -> str:
    """H3: the judge reads the reply, the checked claims and their records (bounded)."""

    claims = json.dumps(checked, ensure_ascii=False)
    if len(claims) > JUDGE_RECORDS:
        claims = claims[:JUDGE_RECORDS] + "…"
    return f"장면: {move}\n\n## 해설자의 답\n{reply}\n\n## 확인된 주장과 기록\n{claims}"


# -- LT-D §5.5: the sentence check at submission -------------------------------------------------


def sentences_of(arguments: dict) -> list[str]:
    """The sentences of a `submit_commentary` call as the server reads it (re-review R3: after
    `normalized`), in order: each item's, or the call's own."""

    arguments = normalized(arguments)
    subjects = arguments["items"] if isinstance(arguments.get("items"), list) else [arguments]
    out = []
    for subject in subjects:
        for sentence in (subject or {}).get("sentences") or [] if isinstance(subject, dict) else []:
            if isinstance(sentence, dict) and isinstance(sentence.get("text"), str):
                out.append(sentence["text"])
    return out


VERDICTS = ("ok", "contradicts", "unbacked")


def _parse_sentences(text: str, count: int) -> list | None:
    """The rows of a sentence check's answer, or None when it is not whole (LT review F2): every
    sentence 1..count judged exactly once, each verdict one of `VERDICTS`. A partial, duplicated or
    misnumbered answer is unreadable, never a pass."""

    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        block = json.loads(match.group(0))
    except ValueError:
        return None
    rows = block.get("sentences") if isinstance(block, dict) else None
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        return None
    numbers = [r.get("n") for r in rows]
    if (
        sorted(n for n in numbers if isinstance(n, int) and not isinstance(n, bool))
        != list(range(1, count + 1))
        or len(numbers) != count
    ):
        return None
    if any(r.get("verdict") not in VERDICTS for r in rows):
        return None
    return rows


def check_sentences(model, system: str, sentences: list[str], checked: list,
                    budget: int | None = None) -> tuple[dict, dict]:  # fmt: skip
    """H5: one request (asked again once when unreadable): each sentence `ok`, `contradicts` or
    `unbacked` against the checked claims."""

    listed = "\n".join(f"{c['n']}. {json.dumps(c['claim'], ensure_ascii=False)} → "
                        f"{json.dumps(c['record'], ensure_ascii=False)[:400]}" for c in checked)  # fmt: skip
    numbered_sentences = "\n".join(f"{i}. {t}" for i, t in enumerate(sentences, start=1))
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": f"## 확인된 주장\n{listed or '(없음)'}\n\n"
                                            f"## 문장\n{numbered_sentences}"}]  # fmt: skip
    usage = {"cost": 0.0, "input_tokens": 0, "output_tokens": 0}
    if not sentences:  # nothing to read: no request
        return {"sentences": [], "bad": []}, usage
    text = ""
    for asked in range(2):
        if (
            asked
            and budget is not None
            and usage["input_tokens"] + usage["output_tokens"] >= budget
        ):
            break
        answer = model.complete(messages, [])
        for key in usage:
            usage[key] += answer.usage.get(key) or 0
        text = answer.message.get("content") or ""
        rows = _parse_sentences(text, len(sentences))
        if rows is not None:
            bad = [r for r in rows if isinstance(r, dict)
                   and r.get("verdict") in ("contradicts", "unbacked")]  # fmt: skip
            return {"sentences": rows, "bad": bad}, usage
    return {"unreadable": True, "raw": text[:500]}, usage


class Gate:
    """HS-D §2 (review B2): `(phase, current_ply)`; a submit passes only at the current moment's
    submit step with every subject the current moment."""

    def __init__(self, session, game: Game, log, game_id: str | None = None) -> None:
        self.session = session
        self.game = game
        self.log = log
        self.game_id = game_id  # HS review F1: a submit names this game, nothing else
        self.phase = "facts"
        self.current_ply: int | None = None
        self.blocked = 0
        self.next_call_id = None  # set by `run._loop` before each call (the checker's id)
        self.submitted = False  # A2: the current moment has an accepted submission
        self.messages = MESSAGES
        self.sentence_check = None  # LT-D §5.5: async (sentences, checked) → (verdict, usage)
        self.checked: list = []  # the moment's checked claims (H2)
        self.holds = 0
        self.hold_on = ("contradicts", "unbacked")  # set by the loop from the revision (A12)
        self.state = "not_run"  # passed | unreadable | exhausted | not_run (re-review R3)
        self.frame_check = None  # AF-D §4: async (arguments) → the frame check's verdict
        self.hide_full = False  # TB-D B3 (rev. 9): `view` dropped from every call
        self.cap: int | None = None  # TB-D B3 (rev. 9): a tool answer above it is refused
        self.accepted: dict[int, list[str]] = {}  # TB-D B1: each moment's accepted sentences
        self.cited: dict[int, list[str]] = {}  # WG-D §3: each accepted subject's cited handles
        self.current_plies: list[int] | None = None  # WG-D §2: a tier-1 batch's plies
        self.tier = 2  # WG-D §4: logged on the frame check's lines
        self.strip_handles = False  # rev. 13: a tier-1 sentence's text loses the handles it names
        self.end_when_all = False  # rev. 13: a batch ends once every ply of it is accepted
        self.short_refs: dict[int, dict[str, str]] | None = None  # rev. 14: short name → handle
        self.sources: dict[int, dict] | None = None  # rev. 15: a digest's scores and ranks → handles

    def new_moment(self) -> None:
        self.checked, self.holds, self.state = [], 0, "not_run"

    def allows(self, arguments: dict) -> tuple[bool, list]:
        arguments = normalized(arguments)  # A3: as the server reads them
        subjects = subjects_of(arguments)
        named = [subject_ply(s, self.game) for s in subjects]
        games = [arguments.get("game")] + [
            s.get("game") for s in subjects if isinstance(s, dict) and "game" in s
        ]
        allowed = set(self.current_plies) if self.current_plies else {self.current_ply}
        ok = (
            self.phase == "submit"
            and bool(subjects)
            and all(g == self.game_id for g in games)
            and all(p is not None and p in allowed for p in named)
        )
        return ok, named

    def done_early(self) -> bool:
        """Rev. 13: the batch has every ply accepted, so the loop needs no further answer."""

        return bool(self.end_when_all and self.current_plies
                    and all(p in self.accepted for p in self.current_plies))  # fmt: skip

    def _shown_plies(self) -> str:
        return ", ".join(map(str, self.current_plies)) if self.current_plies else str(self.current_ply)

    async def call_tool(self, name, arguments):
        if self.hide_full and isinstance(arguments, dict) and "view" in arguments:  # TB-D B3
            arguments = {k: v for k, v in arguments.items() if k != "view"}
            self.log.write({"type": "view_dropped", "tool_call_id": self.next_call_id,
                            "tool": name})  # fmt: skip
        if name == "submit_commentary":
            ok, named = self.allows(arguments if isinstance(arguments, dict) else {})
            if not ok:
                self.blocked += 1
                self.log.write({"type": "tool_unsent", "tool_call_id": self.next_call_id,
                                "tool": name, "reason": "harness_gate",
                                "phase": self.phase, "current_ply": self.current_ply,
                                "subjects": named})  # fmt: skip
                key = "tier1_gate" if self.current_plies else "gate"
                text = self.messages[key].format(ply=self._shown_plies())
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=text)], isError=True
                )
            if self.current_plies and self.short_refs is not None and isinstance(arguments, dict):
                arguments, resolved = resolve_short_handles(arguments, self.short_refs,
                                                            self.game)  # fmt: skip
                if resolved:  # rev. 14: "j7" cites nothing the server knows (S2)
                    self.log.write({"type": "handles_resolved", "tool_call_id": self.next_call_id,
                                    "count": resolved})  # fmt: skip
            if self.current_plies and self.strip_handles and isinstance(arguments, dict):
                arguments, removed = strip_cited_handles(arguments)
                if removed:  # rev. 13: "(j11)" in the text refuses the sentence (S3)
                    self.log.write({"type": "handles_stripped", "tool_call_id": self.next_call_id,
                                    "count": removed})  # fmt: skip
            if self.current_plies and self.sources is not None and isinstance(arguments, dict):
                arguments, added = complete_cites(arguments, self.sources, self.game)
                if added:  # rev. 15: "+6.99" citing only the judgement is refused (S3)
                    self.log.write({"type": "cites_completed", "tool_call_id": self.next_call_id,
                                    "count": len(added), "added": added})  # fmt: skip
            held = await self._sentences(arguments if isinstance(arguments, dict) else {})
            if held is not None:
                return held
        result = await self.session.call_tool(name, arguments)
        text = "\n".join(getattr(c, "text", "") for c in (result.content or [])
                         if getattr(c, "type", None) == "text")  # fmt: skip
        if name == "submit_commentary":  # A2: did the current moment get in?
            if accepted(text):
                self.submitted = True
                for ply, sentences, cites in accepted_subjects(normalized(arguments), text,
                                                               self.game, self.current_ply):  # fmt: skip
                    self.accepted[ply] = sentences
                    self.cited[ply] = cites
        elif self.cap is not None and len(text.encode("utf-8")) > self.cap:  # TB-D B3
            size = len(text.encode("utf-8"))
            ref = str((arguments or {}).get("ref") or "") if isinstance(arguments, dict) else ""
            detail = "refused_detail" if ref.startswith("x") else "refused_other"  # review N3
            key = {"detail": detail, "explore": "refused_length",
                   "compare_lines": "refused_length", "game_overview": "refused_overview",
                   "facts": "refused_facts"}.get(name, "refused_other")  # fmt: skip
            self.log.write({"type": "tool_refused", "tool_call_id": self.next_call_id,
                            "tool": name, "bytes": size, "cap": self.cap})  # fmt: skip
            if self.current_plies and "tier1_refused" in self.messages:  # WG-D §2
                key = "tier1_refused"
            message = self.messages[key].format(tool=name, size=size)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=message)],
                                   isError=True)  # fmt: skip
        return result

    async def _sentences(self, arguments: dict):
        """H5: the call's sentences against the moment's checked claims; a hold answers the agent
        and logs `tool_unsent` (`reason: "sentence_check"`); after `HOLDS` holds the call goes
        unchecked (`exhausted`); an unreadable check sends it (`unreadable`)."""

        if self.frame_check is not None:
            return await self._frames(arguments)
        if self.sentence_check is None:
            return None
        if self.holds >= HOLDS:
            self.state = "exhausted"
            self.log.write({"type": "sentences", "ply": self.current_ply,
                            "call": self.next_call_id, "state": "exhausted"})  # fmt: skip
            return None
        verdict, usage = await self.sentence_check(sentences_of(arguments), self.checked)
        line = {"type": "sentences", "ply": self.current_ply, "call": self.next_call_id,
                "verdict": verdict, "usage": usage}  # fmt: skip
        if verdict.get("unreadable"):
            self.state = "unreadable"
            self.log.write(line | {"state": self.state})
            return None
        held = [r for r in verdict.get("bad") or [] if r.get("verdict") in self.hold_on]
        line["unbacked"] = sum(
            1 for r in verdict.get("bad") or [] if r.get("verdict") == "unbacked"
        )
        if not held:
            self.state = "passed"
            self.log.write(line | {"state": self.state})
            return None
        self.holds += 1
        self.log.write(line | {"state": "held"})
        self.log.write({"type": "tool_unsent", "tool_call_id": self.next_call_id,
                        "tool": "submit_commentary", "reason": "sentence_check",
                        "phase": self.phase, "current_ply": self.current_ply})  # fmt: skip
        problems = "; ".join(f"문장 {r.get('n')}: {r.get('verdict')}"
                             + (f" (주장 {r['claim']})" if r.get("claim") else "")
                             + (f" — {r['why']}" if r.get("why") else "")
                             for r in held)  # fmt: skip
        text = self.messages["held"].format(problems=problems)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=True)

    async def _frames(self, arguments: dict):
        """AF-D §4.2: the frame check (code); a hold answers the agent and logs `tool_unsent`
        (`reason: "frame_check"`); after `HOLDS` holds the call is still checked, passively —
        what it would hold is logged as `unsent_holds` — and sent (`exhausted`, PR #164 F2)."""

        verdict = await self.frame_check(arguments)
        if self.holds >= HOLDS:  # PR #164 F2: checked passively, sent whatever it finds
            self.state = "exhausted"
            self.log.write({"type": "frames", "ply": self.current_ply, "call": self.next_call_id,
                            "tier": self.tier, "plies": self.current_plies,
                            "state": "exhausted", "unsent_holds": verdict["held"],
                            "uncheckable": verdict["uncheckable"],
                            "ambiguous": verdict.get("ambiguous", []),
                            "search_numbers": verdict["search_numbers"],
                            "version": verdict["version"]})  # fmt: skip
            return None
        line = {"type": "frames", "ply": self.current_ply, "call": self.next_call_id,
                "tier": self.tier, "plies": self.current_plies, "held": verdict["held"], "uncheckable": verdict["uncheckable"],
                "ambiguous": verdict.get("ambiguous", []),
                "search_numbers": verdict["search_numbers"], "version": verdict["version"]}  # fmt: skip
        if not verdict["held"]:
            self.state = "passed"
            self.log.write(line | {"state": self.state})
            return None
        self.holds += 1
        self.log.write(line | {"state": "held"})
        self.log.write({"type": "tool_unsent", "tool_call_id": self.next_call_id,
                        "tool": "submit_commentary", "reason": "frame_check",
                        "phase": self.phase, "current_ply": self.current_ply})  # fmt: skip
        problems = "; ".join(f"문장 {h['sentence']} ({h['rule']}): {h['reply']}"
                             for h in verdict["held"])  # fmt: skip
        text = self.messages["held"].format(problems=problems)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=True)

    def __getattr__(self, item):
        return getattr(self.session, item)


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}
    for candidate in (match.group(0), match.group(0).replace('\\"', '"')):
        try:
            verdict = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(verdict, dict) and isinstance(verdict.get("pass"), bool):
            return verdict
    return {}


def judge(model, header: str, reply: str, budget: int | None = None,
          system: str | None = None, content: str | None = None) -> tuple[dict, dict]:  # fmt: skip
    """HS-D §3: one request on the run's model, no tools; the moment's header and the agent's reply
    only (rev. 5: also the checked claims and their records, `content`). An answer that is not the
    JSON asked for is asked again once; still unreadable, it never blocks the moment. `budget`: the
    tokens the run has left (HS review R2): the re-ask is not sent once the first answer used them
    up."""

    user = content if content is not None else f"{header}\n\n## 해설자의 답\n{reply}"
    messages = [{"role": "system", "content": system or JUDGES[4]},
                {"role": "user", "content": user}]  # fmt: skip
    usage = {"cost": 0.0, "input_tokens": 0, "output_tokens": 0}
    text = ""
    for asked in range(2):
        if (
            asked
            and budget is not None
            and usage["input_tokens"] + usage["output_tokens"] >= budget
        ):
            return {"pass": False, "problems": [], "unreadable": True, "budget": True,
                    "raw": text[:500]}, usage  # fmt: skip
        answer = model.complete(messages, [])
        for key in usage:
            usage[key] += answer.usage.get(key) or 0
        if getattr(answer, "cut", False):  # TB-D C4 (review N4): a cut judge answer is recorded
            usage["cut"] = usage.get("cut", 0) + 1
        text = answer.message.get("content") or ""
        verdict = _parse(text)
        if verdict:
            verdict["problems"] = [str(p) for p in (verdict.get("problems") or [])][:3]
            return verdict, usage
    return {"pass": False, "problems": [], "unreadable": True, "raw": text[:500]}, usage


def last_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant" and message.get("content"):
            return message["content"]
    return ""


async def harness_loop(session, model, messages, tools, spec, log, totals, plain_loop, judge_model,
                       moments: list[tuple[int, str]]) -> str:  # fmt: skip
    """The stages over the fixed moments, in game order (HS-D §2). `moments`: (ply, numbered move)."""

    rev = revision_of(spec)
    if rev in PER_MOMENT:
        return await harness_loop_v9(session, model, messages, tools, spec, log, totals,
                                     plain_loop, judge_model, moments)  # fmt: skip
    texts = ALL_MESSAGES[rev]
    gate = Gate(session, Game(spec.pgn), log, spec.game_id)
    gate.messages = texts
    gate.hold_on = HOLD_ON.get(rev, ("contradicts", "unbacked"))

    def count(usage: dict) -> None:
        # HS review F2: the judge's (and LT's sentence check's) tokens count against the run's token
        # bound with the agent's; `judge_*` keep their share apart. The turn bound counts the
        # agent's requests only.
        totals["input_tokens"] += usage["input_tokens"]
        totals["output_tokens"] += usage["output_tokens"]
        totals["cost"] += usage["cost"]
        totals["judge_cost"] = totals.get("judge_cost", 0.0) + usage["cost"]
        totals["judge_tokens"] = (totals.get("judge_tokens", 0) + usage["input_tokens"]
                                  + usage["output_tokens"])  # fmt: skip

    if SENTENCE_SYSTEMS[rev]:

        async def sentence_check(sentences, checked):
            left = spec.bounds.tokens - totals["input_tokens"] - totals["output_tokens"]
            if left <= 0:
                return {"unreadable": True, "budget": True}, {"cost": 0.0, "input_tokens": 0,
                                                              "output_tokens": 0}  # fmt: skip
            verdict, usage = await anyio.to_thread.run_sync(
                check_sentences, judge_model, SENTENCE_SYSTEMS[rev], sentences, checked, left,
                abandon_on_cancel=True,
            )  # fmt: skip
            count(usage)
            return verdict, usage

        gate.sentence_check = sentence_check
    if FRAMES.get(rev):  # AF-D §4: the frame check reads the cited records through `detail`

        async def frame_check(arguments):
            from . import frames

            args = normalized(arguments)
            records = {}
            for ref in sorted(frames.refs_needed(args)):
                records[ref] = await read_record(session, spec.game_id, ref, log,
                                                 gate.next_call_id)  # fmt: skip
            return frames.check(args, records, FRAMES[rev])

        gate.frame_check = frame_check
    sent = 0  # the first request logs the system message and the task (HS-D §4)
    for ply, move in moments:
        gate.current_ply, gate.phase = ply, "facts"
        gate.new_moment()
        messages.append({"role": "user", "content": texts["facts"].format(move=move)})
        how = texts["passed"]
        attempt = 0
        while True:
            log.write({"type": "harness", "stage": "facts", "ply": ply, "attempt": attempt})
            reason = await plain_loop(gate, model, messages, tools, spec, log, totals, {}, sent)
            sent = len(messages)
            if reason != "done":
                return reason
            reply = last_text(messages)
            used = totals["input_tokens"] + totals["output_tokens"]
            if used >= spec.bounds.tokens:  # HS review R2: no judge request past the bound
                return "tokens"
            content, retry = None, "retry"
            if rev >= 5:  # LT-D §5.2: the checker before the judge
                results, problems, checked = await check_claims(
                    session, spec.game_id, claims_of(reply), log
                )
                log.write({"type": "harness", "stage": "check", "ply": ply, "attempt": attempt,
                           "results": results, "problems": problems})  # fmt: skip
                gate.checked = checked
                if problems:
                    verdict = {"pass": False, "problems": problems, "by": "check"}
                    retry = "check"
                else:
                    content = judge_input(move, reply, checked)
            if retry == "retry":
                verdict, usage = await anyio.to_thread.run_sync(  # abandoned at the bound (N1)
                    judge,
                    judge_model,
                    f"장면: {move}",
                    reply,
                    spec.bounds.tokens - used,
                    JUDGES[rev],
                    content,
                    abandon_on_cancel=True,
                )
                count(usage)
                log.write({"type": "judge", "ply": ply, "attempt": attempt, "verdict": verdict,
                           "usage": usage, "reply": reply})  # fmt: skip
            if verdict["pass"] or verdict.get("unreadable"):
                break
            if attempt >= RETRIES:
                how = texts["exhausted"]
                break
            attempt += 1
            problems = "; ".join(verdict.get("problems") or [])
            messages.append(
                {"role": "user", "content": texts[retry].format(move=move, problems=problems)}
            )
        gate.phase, gate.submitted = "submit", False
        messages.append({"role": "user", "content": texts["submit"].format(move=move, how=how)})
        log.write({"type": "harness", "stage": "submit", "ply": ply, "attempts": attempt + 1})
        asks = 0
        while True:  # A2: the step ends with the moment accepted, or after SUBMIT_ASKS re-asks
            reason = await plain_loop(gate, model, messages, tools, spec, log, totals, {}, sent)
            sent = len(messages)
            if reason != "done":
                return reason
            if gate.submitted:
                break
            if asks >= SUBMIT_ASKS:
                log.write({"type": "harness", "stage": "submit_missing", "ply": ply, "asks": asks})
                break
            asks += 1
            log.write({"type": "harness", "stage": "submit_again", "ply": ply, "ask": asks})
            messages.append({"role": "user",
                             "content": texts["unsubmitted"].format(move=move, ply=ply)})  # fmt: skip
        if gate.sentence_check is not None or gate.frame_check is not None:  # the moment's state
            log.write({"type": "harness", "stage": "sentence_state", "ply": ply,
                       "state": gate.state, "holds": gate.holds})  # fmt: skip
    log.write({"type": "harness", "stage": "end", "blocked_submissions": gate.blocked})
    return "done"


# -- TB-D §3: rev. 9, a conversation per moment, the guard, the moment's ends -----------------------


def harness_tools(tools: list[dict]) -> list[dict]:
    """TB-D B2, B3: the tools a rev. 9 harness serves, their schemas without `view`."""

    out = []
    for tool in tools:
        f = tool["function"]
        if f["name"] not in HARNESS_TOOLS:
            continue
        schema = json.loads(json.dumps(f.get("parameters") or {}))
        (schema.get("properties") or {}).pop("view", None)
        if isinstance(schema.get("required"), list) and "view" in schema["required"]:
            schema["required"] = [r for r in schema["required"] if r != "view"]
        out.append({"type": "function", "function": f | {"parameters": schema}})
    return out


def story_of(accepted: dict[int, list[str]], moves: dict[int, str], keep: int = 4) -> str:
    """TB-D B1: the earlier moments' accepted sentences, prose only; past `keep` moments the older
    ones keep their first sentence."""

    plies = sorted(accepted)
    out = []
    for i, ply in enumerate(plies):
        sentences = accepted[ply]
        if len(plies) - i > keep:
            sentences = sentences[:1]
        out.append(f"{moves.get(ply, ply)}: " + " ".join(sentences))
    return "\n".join(out)


async def harness_loop_v9(session, model, messages, tools, spec, log, totals, plain_loop,
                          judge_model, moments: list[tuple[int, str]]) -> str:  # fmt: skip
    """TB-D §3: rev. 8's stages, each moment in a conversation of its own (B1), behind the guard
    (B4) with one compaction a moment, and moment ends apart from the run's (B7)."""

    from .guard import NOTES_LIMIT, Guard

    rev = revision_of(spec)
    texts = ALL_MESSAGES[rev]
    gate = Gate(session, Game(spec.pgn), log, spec.game_id)
    gate.messages = texts
    gate.hide_full, gate.cap = True, ANSWER_CAP
    guard = Guard(log)
    base = [dict(m) for m in messages]  # the system message and the task
    moves = dict(moments)

    def count(usage: dict) -> None:
        totals["input_tokens"] += usage["input_tokens"]
        totals["output_tokens"] += usage["output_tokens"]
        totals["cost"] += usage["cost"] or 0.0
        totals["judge_cost"] = totals.get("judge_cost", 0.0) + (usage["cost"] or 0.0)
        totals["judge_tokens"] = (totals.get("judge_tokens", 0) + usage["input_tokens"]
                                  + usage["output_tokens"])  # fmt: skip

    async def frame_check(arguments):
        from . import frames

        args = normalized(arguments)
        records = {}
        for ref in sorted(frames.refs_needed(args)):
            records[ref] = await read_record(session, spec.game_id, ref, log,
                                             gate.next_call_id)  # fmt: skip
        return frames.check(args, records, FRAMES[rev])

    gate.frame_check = frame_check
    # `facts`: the moment's last facts reply; `passed`: whether the judge passed it (review N1)
    state = {"sent": 0, "last_runner": None, "facts": None, "passed": False, "ply": None}

    def runner(content: str) -> None:
        messages.append({"role": "user", "content": content})
        state["last_runner"] = content

    def rebuild(extra: list[str]) -> None:
        """B1, B7: the moment's list from its parts, logged once; `sent` is its length (N3)."""

        story = story_of({p: s for p, s in gate.accepted.items() if p != state["ply"]}, moves)
        parts = [dict(m) for m in base]
        if story:
            parts.append({"role": "user", "content": texts["story"].format(story=story)})
        parts += [{"role": "user", "content": x} for x in extra]
        messages[:] = parts
        state["sent"] = len(messages)

    def over_budget() -> bool:
        return totals["input_tokens"] + totals["output_tokens"] >= spec.bounds.tokens or (
            spec.bounds.cost is not None and totals["cost"] >= spec.bounds.cost
        )

    async def compact() -> str | None:
        """B4.3: notes from the last list within the limit, then the moment's restart. None when
        the moment restarted; otherwise the end (`moment_budget`, `moment_refused`, a run bound)."""

        full = list(messages)
        last = max((i for i, m in enumerate(full) if m.get("role") == "assistant"), default=None)
        prefixes = [full] + ([full[:last]] if last is not None else [])
        if guard.last_size > guard.limit(guard.last_how) and last is not None:
            prefixes = [full[:last]]  # the last answer and its tool answers pushed it over
        ask = None
        for prefix in prefixes:  # review F3: the cut prefix is tried when the whole one is over
            trial = prefix + [{"role": "user", "content": texts["compact"]}]
            size, how = await anyio.to_thread.run_sync(guard.size, model, trial, tools, "none",
                                                       abandon_on_cancel=True)  # fmt: skip
            log.write({"type": "compact", "ply": state["ply"], "counted_tokens": size,
                       "how": how, "cut_at": len(prefix) if len(prefix) < len(full) else None})  # fmt: skip
            if size <= guard.limit(how):
                ask = trial
                break
        if ask is None:
            return "moment_budget"
        notes = None
        for attempt in range(2):
            if over_budget():  # review N2: the run's bounds hold for compaction too
                return (
                    "cost"
                    if spec.bounds.cost is not None and totals["cost"] >= spec.bounds.cost
                    else "tokens"
                )
            log.write(
                {
                    "type": "request",
                    "stage": "compact",
                    "messages": ask,
                    "tools_offered": len(tools),
                }
            )  # fmt: skip  review F5
            reply = await anyio.to_thread.run_sync(_complete_none, model, ask, tools,
                                                   abandon_on_cancel=True)  # fmt: skip
            guard.answered(reply.usage, len(ask))
            totals["turns"] += 1
            for k in ("input_tokens", "output_tokens"):
                totals[k] += reply.usage.get(k) or 0
            totals["cost"] += reply.usage.get("cost") or 0.0
            log.write({"type": "response", "stage": "compact", "message": reply.message,
                       "usage": reply.usage})  # fmt: skip
            text = reply.message.get("content") or ""
            if getattr(reply, "refused", False):
                return "moment_refused"
            if getattr(reply, "cut", False) or not text:
                return "moment_budget"
            size_notes, _ = await anyio.to_thread.run_sync(
                guard.size, model, [{"role": "user", "content": text}], [], None,
                abandon_on_cancel=True)  # fmt: skip
            if size_notes <= NOTES_LIMIT:
                notes = text
                break
            log.write({"type": "notes_long", "ply": state["ply"], "tokens": size_notes})
            if attempt:
                return "moment_budget"
            kept = {
                "role": "assistant",
                "content": text,
            }  # review F2: its blocks sent back as given
            for key in ("blocks", "reasoning", "reasoning_details"):
                if key in reply.message:
                    kept[key] = reply.message[key]
            ask = ask + [kept, {"role": "user", "content": texts["notes_long"]}]
            size, how = await anyio.to_thread.run_sync(guard.size, model, ask, tools, "none",
                                                       abandon_on_cancel=True)  # fmt: skip
            log.write({"type": "compact", "ply": state["ply"], "counted_tokens": size,
                       "how": how, "ask": "notes_long"})  # fmt: skip
            if size > guard.limit(how):  # review F2: the re-ask is counted like any request
                return "moment_budget"
        extra = [texts["notes"].format(notes=notes)]
        if state["facts"]:
            key = "passed_facts" if state["passed"] else "last_facts"
            extra.append(texts[key].format(facts=state["facts"]))
        if state["last_runner"]:
            extra.append(state["last_runner"])
        rebuild(extra)
        guard.restarted = True
        log.write({"type": "restart", "ply": state["ply"], "messages": messages})
        return None

    async def step() -> str:
        """The plain loop under the guard; a compaction restarts the moment once (B4.3)."""

        while True:
            reason = await plain_loop(gate, model, messages, tools, spec, log, totals, {},
                                      state["sent"], guard=guard)  # fmt: skip
            state["sent"] = len(messages)
            if reason != "compact":
                return reason
            if guard.restarted:
                return "moment_budget"
            end = await compact()
            if end is not None:
                return end

    for ply, move in moments:
        gate.current_ply, gate.phase = ply, "facts"
        gate.new_moment()
        gate.submitted = False
        guard.new_moment()
        state.update(ply=ply, facts=None, passed=False, last_runner=None)
        rebuild([])
        log.write({"type": "moment_start", "ply": ply, "messages": messages})
        runner(texts["facts"].format(move=move))
        how = texts["passed"]
        attempt = 0
        reason = None
        while True:
            log.write({"type": "harness", "stage": "facts", "ply": ply, "attempt": attempt})
            reason = await step()
            if reason != "done":
                break
            reply = last_text(messages)
            if over_budget():
                reason = (
                    "cost"
                    if spec.bounds.cost is not None and totals["cost"] >= spec.bounds.cost
                    else "tokens"
                )
                break
            results, problems, checked = await check_claims(session, spec.game_id,
                                                            claims_of(reply), log)  # fmt: skip
            log.write({"type": "harness", "stage": "check", "ply": ply, "attempt": attempt,
                       "results": results, "problems": problems})  # fmt: skip
            gate.checked = checked
            retry = "retry"
            if problems:
                verdict = {"pass": False, "problems": problems, "by": "check"}
                retry = "check"
            else:
                verdict, usage = await anyio.to_thread.run_sync(
                    judge, judge_model, f"장면: {move}", reply, None, JUDGES[rev],
                    judge_input(move, reply, checked), abandon_on_cancel=True)  # fmt: skip
                count(usage)
                log.write({"type": "judge", "ply": ply, "attempt": attempt, "verdict": verdict,
                           "usage": usage, "reply": reply})  # fmt: skip
            state["facts"] = reply
            if verdict["pass"] or verdict.get("unreadable"):
                state["passed"] = bool(verdict["pass"])  # review N1: unreadable is not passed
                break
            if attempt >= RETRIES:
                how = texts["exhausted"]
                break
            attempt += 1
            runner(
                texts[retry].format(move=move, problems="; ".join(verdict.get("problems") or []))
            )
        if reason in MOMENT_ENDS:
            log.write({"type": "harness", "stage": "moment_end", "ply": ply, "reason": reason,
                       "at": "facts"})  # fmt: skip
            continue
        if reason != "done":
            return reason
        gate.phase, gate.submitted = "submit", False
        runner(texts["submit"].format(move=move, how=how))
        log.write({"type": "harness", "stage": "submit", "ply": ply, "attempts": attempt + 1})
        asks = 0
        while True:
            reason = await step()
            if reason != "done":
                break
            if gate.submitted:
                break
            if asks >= SUBMIT_ASKS:
                log.write({"type": "harness", "stage": "submit_missing", "ply": ply, "asks": asks})
                break
            asks += 1
            log.write({"type": "harness", "stage": "submit_again", "ply": ply, "ask": asks})
            runner(texts["unsubmitted"].format(move=move, ply=ply))
        log.write({"type": "harness", "stage": "sentence_state", "ply": ply,
                   "state": gate.state, "holds": gate.holds})  # fmt: skip
        if reason in MOMENT_ENDS:
            log.write({"type": "harness", "stage": "moment_end", "ply": ply, "reason": reason,
                       "at": "submit"})  # fmt: skip
            continue
        if reason != "done":
            return reason
        log.write({"type": "harness", "stage": "moment_end", "ply": ply,
                   "reason": "submitted" if gate.submitted else "unsubmitted"})  # fmt: skip
    if rev in TIERED:  # WG-D: tier 1's batches, then tier 0
        reason = await whole_game(session, model, tools, spec, log, totals, plain_loop, gate, guard,
                                  texts, over_budget)  # fmt: skip
        if reason != "done":
            return reason
    log.write({"type": "harness", "stage": "end", "blocked_submissions": gate.blocked})
    return "done"


async def _call_text(session, game_id: str, tool: str, arguments: dict, log) -> str | None:
    """The harness's own call (`harness_call`, logged so the run checker pairs it)."""

    log.write({"type": "harness_call", "tool": tool} | {k: v for k, v in arguments.items()
                                                         if k != "game"})  # fmt: skip
    result = await session.call_tool(tool, {"game": game_id} | arguments)
    if getattr(result, "isError", False):
        return None
    return "\n".join(getattr(c, "text", "") for c in (result.content or [])
                     if getattr(c, "type", None) == "text")  # fmt: skip


async def overview_lines(session, game_id: str, plies: int, log) -> list[dict]:
    """WG-D §1: every ply's `game_overview` line, in ranges of `LINES_LIMIT`."""

    out = []
    for start in range(1, plies + 1, 200):
        text = await _call_text(session, game_id, "game_overview",
                                {"plies": f"{start}-{min(start + 199, plies)}"}, log)  # fmt: skip
        answer = json.loads(text) if text else {}
        out += [x for x in answer.get("lines") or [] if isinstance(x, dict) and "ply" in x]
    return out


def _totals_since(totals: dict, before: dict) -> dict:
    keys = ("turns", "tool_calls", "input_tokens", "output_tokens", "cost")
    return {k: round(totals.get(k, 0) - before.get(k, 0), 6) for k in keys}


async def whole_game(session, model, tools, spec, log, totals, plain_loop, gate, guard, texts,
                     over_budget) -> str:  # fmt: skip
    """WG-D §1–§4: the tiers from `game_overview`, tier 1 a batch a conversation (§2), tier 0's
    followed-line sentence (§3), the `tiers` line (§4), written however the run ends. The run's
    reason, or `done`."""

    from dataclasses import replace

    from . import tiers as tiering
    from .guard import Guard

    after_tier2 = dict(totals)
    game = Game(spec.pgn)
    ucis = list(game.uci)
    sans = numbered_sans(spec.pgn)
    lines = await overview_lines(session, spec.game_id, len(ucis), log)
    tier_of = tiering.tiers_of(lines, list(spec.moments))
    tier1 = sorted(p for p, t in tier_of.items() if t == 1)
    sampled = tiering.sample(lines, tier_of)
    tier_tools = [x for x in tools if x["function"]["name"] in TIER1_TOOLS]
    rev = revision_of(spec)
    system = (PROMPTS / f"{TIER1_GUIDES[rev]}.md").read_text(encoding="utf-8")
    gate.strip_handles = gate.end_when_all = rev in LEAN_TIER1
    gate.short_refs = {} if rev in SHORT_HANDLES else None
    gate.sources = {} if rev in COMPLETE_CITES else None
    log.write({"type": "tiers_plan", "tier1": tier1, "sample": sampled,
               "counts": {str(k): sum(1 for t in tier_of.values() if t == k) for k in (0, 1, 2)}})  # fmt: skip
    ends: dict[str, str] = {}
    notes: list[dict] = []
    marks = {"after_tier1": None}

    def summary(reason: str) -> None:
        """§4: the `tiers` line, also when the run ends inside tier 1 (review, slice 4 F2)."""

        after_tier1 = marks["after_tier1"] or dict(totals)
        for ply in tier1:
            ends.setdefault(str(ply), "not_run")
        log.write({"type": "tiers", "reason": reason, "tier1": tier1, "sample": sampled,
                   "ends": ends, "tier0_sentences": len(notes),
                   "coverage": {"plies": len(ucis),
                                "tier2": sum(1 for p, t in tier_of.items() if t == 2 and p in gate.accepted),
                                "tier1": sum(1 for p in tier1 if p in gate.accepted),
                                "tier1_asked": len(tier1), "tier0_sentences": len(notes)},
                   "totals": {"tier2": _totals_since(after_tier2, {}),
                              "tier1": _totals_since(after_tier1, after_tier2),
                              "tier0": _totals_since(totals, after_tier1)}})  # fmt: skip

    try:
        reason = await _tier_one(session, model, spec, log, totals, plain_loop, gate, texts,
                                 over_budget, tiering.batches(tier1), tier_tools, system, sans,
                                 ends, Guard(log), replace)  # fmt: skip
    except BaseException as error:  # RV-1 P5-3: a timeout or a cancel still writes the line
        summary(type(error).__name__)
        raise
    gate.current_plies, gate.tier = None, 2
    if reason != "done":
        summary(reason)
        return reason
    marks["after_tier1"] = dict(totals)
    for ply in sorted(gate.accepted):
        records = []
        for ref in gate.cited.get(ply, []):
            if ref[:1] in ("x", "s"):
                _kind, item = await read_record(session, spec.game_id, ref.split(":", 1)[0], log)
                if isinstance(item, dict):
                    records.append((ref, item))
        note = tiering.followed_sentence(ucis, sans, ply, tier_of, records)
        if note is not None and all(n["ply"] != note["ply"] for n in notes):
            notes.append(note)
            log.write({"type": "tier0", **note})
    summary("done")
    return "done"


async def _tier_one(session, model, spec, log, totals, plain_loop, gate, texts, over_budget,
                    queue, tier_tools, system, sans, ends, guard, replace) -> str:  # fmt: skip
    """WG-D §2: each batch one conversation; `done`, or the reason that ends the run."""

    from . import tiers as tiering

    digests: dict[int, str] = {}  # a halved batch does not fetch its digests again (review)
    while queue:
        batch = queue.pop(0)
        if over_budget():
            return ("cost" if spec.bounds.cost is not None and totals["cost"] >= spec.bounds.cost
                    else "tokens")  # fmt: skip
        for ply in batch:
            if ply not in digests:
                text = await _call_text(session, spec.game_id, "ply", {"ply": ply}, log)
                if gate.short_refs is not None:
                    gate.short_refs[ply] = short_names(text or "")
                if gate.sources is not None:
                    gate.sources[ply] = digest_sources(text or "")
                digests[ply] = texts["tier1_digest"].format(move=sans[ply - 1], ply=ply,
                                                            digest=text or "(없음)")  # fmt: skip
        story = story_of({p: s for p, s in gate.accepted.items() if p < batch[0]},
                         {p: sans[p - 1] for p in gate.accepted})  # fmt: skip
        first = [texts["tier1_task"].format(count=len(batch), game_id=spec.game_id,
                                            moves=", ".join(f"{sans[p - 1]} (ply {p})" for p in batch))]  # fmt: skip
        if story:
            first.append(texts["tier1_story"].format(story=story))
        first += [digests[p] for p in batch]
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": "\n\n".join(first)}]  # fmt: skip
        guard.new_moment()  # review: the split's count never reuses the last batch's usage
        size, how = await anyio.to_thread.run_sync(guard.size, model, messages, tier_tools, None,
                                                   abandon_on_cancel=True)  # fmt: skip
        if size > TIER1_FIRST and len(batch) > 1:
            log.write({"type": "batch_split", "plies": batch, "counted_tokens": size, "how": how})
            queue[:0] = tiering.halves(batch)
            continue
        gate.new_moment()
        gate.current_ply, gate.current_plies, gate.tier = None, batch, 1
        gate.phase, gate.submitted = "submit", False
        guard.restarted = True  # WG-D §2: no compaction in a batch; over the limit it ends
        log.write({"type": "batch_start", "tier": 1, "plies": batch, "counted_tokens": size,
                   "how": how, "messages": messages})  # fmt: skip
        bound = replace(spec, bounds=replace(spec.bounds,
                                             turns=min(spec.bounds.turns, totals["turns"] + TIER1_TURNS)))  # fmt: skip
        sent, asks = 0, 0
        while True:
            reason = await plain_loop(gate, model, messages, tier_tools, bound, log, totals, {}, sent,
                                      guard=guard)  # fmt: skip
            sent = len(messages)
            if reason == "turns" and totals["turns"] < spec.bounds.turns:
                reason = "batch_turns"
            if reason != "done" or gate.submitted:
                break
            if asks >= TIER1_ASKS:
                reason = "unsubmitted"
                break
            asks += 1
            messages.append({"role": "user",
                             "content": texts["tier1_unsubmitted"].format(ply=gate._shown_plies())})  # fmt: skip
        got = [p for p in batch if p in gate.accepted]
        end = "submitted" if got else (reason if reason != "done" else "unsubmitted")
        for ply in batch:
            ends[str(ply)] = "submitted" if ply in got else ("left_out" if got else end)
        log.write({"type": "batch_end", "tier": 1, "plies": batch, "accepted": got,
                   "reason": reason, "state": gate.state, "holds": gate.holds})  # fmt: skip
        if reason not in ("done", "batch_turns", "unsubmitted", *MOMENT_ENDS):
            return reason
    return "done"


def numbered_sans(pgn: str) -> list[str]:
    """Every ply's numbered SAN (`14...Qb3`), in order."""

    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()
    out = []
    for index, move in enumerate(game.mainline_moves(), start=1):
        number = (index + 1) // 2
        out.append(f"{number}{'.' if index % 2 else '...'}{board.san(move)}")
        board.push(move)
    return out


def _complete_none(model, messages, tools):
    """B4.3: the compaction request, tools sent (the cached prefix holds) with `tool_choice` none."""

    import inspect

    if "tool_choice" in inspect.signature(model.complete).parameters:  # review N2: no catch-all
        return model.complete(messages, tools, tool_choice="none")
    return model.complete(messages, tools)
