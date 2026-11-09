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
}
FRAMES = {8: "harness_frames_v1"}  # AF-D §4.4: the revisions with the frame check (code)
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


async def read_record(session, game_id: str, ref, log) -> tuple[str | None, object]:
    """A record through the server's `detail`, as the harness's own call (`harness_call`, review
    F3): logged so the run checker pairs it with the server's line; never shown to the agent."""

    if not isinstance(ref, str):
        return None, None
    log.write({"type": "harness_call", "tool": "detail", "ref": ref})
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

    def new_moment(self) -> None:
        self.checked, self.holds, self.state = [], 0, "not_run"

    def allows(self, arguments: dict) -> tuple[bool, list]:
        arguments = normalized(arguments)  # A3: as the server reads them
        subjects = subjects_of(arguments)
        named = [subject_ply(s, self.game) for s in subjects]
        games = [arguments.get("game")] + [
            s.get("game") for s in subjects if isinstance(s, dict) and "game" in s
        ]
        ok = (
            self.phase == "submit"
            and bool(subjects)
            and all(g == self.game_id for g in games)
            and all(p is not None and p == self.current_ply for p in named)
        )
        return ok, named

    async def call_tool(self, name, arguments):
        if name == "submit_commentary":
            ok, named = self.allows(arguments if isinstance(arguments, dict) else {})
            if not ok:
                self.blocked += 1
                self.log.write({"type": "tool_unsent", "tool_call_id": self.next_call_id,
                                "tool": name, "reason": "harness_gate",
                                "phase": self.phase, "current_ply": self.current_ply,
                                "subjects": named})  # fmt: skip
                text = self.messages["gate"].format(ply=self.current_ply)
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=text)], isError=True
                )
            held = await self._sentences(arguments if isinstance(arguments, dict) else {})
            if held is not None:
                return held
        result = await self.session.call_tool(name, arguments)
        if name == "submit_commentary":  # A2: did the current moment get in?
            text = "\n".join(getattr(c, "text", "") for c in (result.content or [])
                             if getattr(c, "type", None) == "text")  # fmt: skip
            if accepted(text):
                self.submitted = True
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
        (`reason: "frame_check"`); after `HOLDS` holds the call goes unchecked (`exhausted`)."""

        if self.holds >= HOLDS:
            self.state = "exhausted"
            self.log.write({"type": "frames", "ply": self.current_ply,
                            "call": self.next_call_id, "state": "exhausted"})  # fmt: skip
            return None
        verdict = await self.frame_check(arguments)
        line = {"type": "frames", "ply": self.current_ply, "call": self.next_call_id,
                "held": verdict["held"], "uncheckable": verdict["uncheckable"],
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
                records[ref] = await read_record(session, spec.game_id, ref, log)
            return frames.check(args, records)

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
