"""The digest of a ply (AG6-D §3): what an agent writes from or cites, the rest one call away.

`ply` and `judge_move` answer it by default; `view: "full"` keeps today's answer. Every item the
full answer serves keeps its handle (served by the session, whether or not the digest shows it),
so verification reads the served item, never the digest (V2). REFUTED claims are named and the
observations counted (V3); bundle digests, curves, policies, search ids and segments are never
shown (V4); a position is given once and a line as SAN (V5). The digest is bounded (§3.6): fields
of free length are capped, then fixed steps move items behind `detail` until it fits, and
`not_shown` says what moved.
"""

from __future__ import annotations

import copy
import json
from decimal import ROUND_HALF_UP, Decimal

from .remarks import claim_proves, en_passant, template_part

DIGEST_LIMIT = 16_000  # characters of the compact JSON `content` (§3.6)
TEXT_CAP = 2_000
SAYS_CAP = 300
FINDING_CAP = 100
PV_PLIES = 8
PV_SHORT = 4  # step 2
OTHERS = 3  # candidates beyond the played and the best move
ROLE_ORDER = ("consequence", "comparison", "mechanism", "function")
MATERIAL_TEMPLATES = ("material_gain_v3", "material_loss_v2")  # the templates with ATTRIBUTED
POSITION_KEYS = frozenset({"node", "from_root", "fen", "position", "target", "line", "lines"})
BEHIND_DETAIL = ("scopes in full", "evidence", "relations", "checks", "PVs beyond the digest's",
                 "the other candidates' PVs")  # fmt: skip
STEPS = ("board", "findings", "short_pv", "inconclusive_named", "text", "supported_named",
         "named_left_out")  # fmt: skip
BOARD_KEEP = {"threat": 2, "weakness": 0, "lost_defence": 2}  # AG8-D §2.3: kept by step 0


class DigestTooLarge(ValueError):
    """A digest still over its bound after every step (§3.6: a fault, never a cut answer)."""


def size(value) -> int:
    """Characters of the compact JSON a tool sends (F12)."""

    return len(compact(value))


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def score_text(score: dict | None) -> str | None:
    """A score as a sentence writes it (the token rules): White's view, pawns with two decimals
    and a sign (`+0.38`, `-1.20`), a mate as `M3` (White mates) or `-M3`."""

    if not score:
        return None
    if score.get("mate") is not None:
        mate = score["mate"]
        return f"M{mate}" if mate > 0 else f"-M{-mate}"
    cp = score.get("cp")
    if cp is None:
        return None
    pawns = (Decimal(abs(cp)) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{'-' if cp < 0 else '+'}{pawns}"


def numbered(move_number: int, side: str, san: str) -> str:
    return f"{move_number}{'.' if side == 'white' else '...'}{san}"


def _cap(text: str | None, cap: int, capped: dict, name: str) -> str | None:
    if text is None or len(text) <= cap:
        return text
    capped[name] = len(text)
    return text[: cap - 1] + "…"


def _without_positions(value, capped: dict, name: str):
    """A finding without the positions it names (V5); its strings capped (§3.6)."""

    if isinstance(value, dict):
        return {k: _without_positions(v, capped, f"{name}.{k}") for k, v in value.items()
                if k not in POSITION_KEYS}  # fmt: skip
    if isinstance(value, list):
        return [_without_positions(v, capped, name) for v in value]
    if isinstance(value, str):
        return _cap(value, FINDING_CAP, capped, name)
    return value


def scope_text(scope: dict) -> str:
    """One effective scope in one line: quantifier/basis, the plies of its line, its depth."""

    text = f"{scope.get('quantifier')}/{scope.get('basis')}"
    at = scope.get("at") or {}
    if at.get("kind") == "line":
        text += f" {at.get('first')}-{at.get('last')}"
    if scope.get("depth"):
        text += f" d{scope['depth']}"
    return text


def _line(line: dict | None, plies: int) -> dict | None:
    if line is None:
        return None
    return {
        "ref": line.get("ref"),
        "move": line["move"]["san"],
        "score": line.get("score"),
        "score_text": score_text(line.get("score")),
        "depth": line.get("depth"),
        "pv": " ".join(p["san"] for p in (line.get("pv") or [])[:plies]),
    }


def _role_rank(claim: dict) -> tuple:
    role = claim.get("role")
    return (ROLE_ORDER.index(role), "") if role in ROLE_ORDER else (len(ROLE_ORDER), role or "")


def _attributed(claim: dict) -> str | None:
    if claim.get("template") not in MATERIAL_TEMPLATES:
        return None
    checks = [c for c in claim.get("checks", ()) if c.get("kind") == "attributed"]
    if not checks:
        return "absent"
    return "passed" if all(c.get("passed") for c in checks) else "failed"


def digest(record: dict, glossary: dict, sentences: dict[str, str] | None = None) -> dict:
    """The digest of a full `ply` / `judge_move` record whose items carry their refs (§3.2).
    `sentences`: a claim's own sentence (`claim_sentence`) for the claims the text left out."""

    capped: dict[str, int] = {}
    said: dict[str, str] = {}
    for segment in record.get("segments", ()):
        if segment.get("source") == "claim" and segment.get("claim"):
            said[segment["claim"]] = (
                said.get(segment["claim"], "") + " " + segment["text"]
            ).strip()
    for claim_id, text in (sentences or {}).items():
        said.setdefault(claim_id, text)
    analysis = record["analysis"]
    subject = analysis["judgements"][0]
    claims, refuted = [], []
    ordered = sorted(enumerate(analysis["claims"]), key=lambda pair: (_role_rank(pair[1]), pair[0]))
    for _, claim in ordered:
        if claim["status"] == "refuted":
            refuted.append({"template": claim["template"], "ref": claim.get("ref")})
            continue
        entry = {
            "ref": claim.get("ref"),
            "template": claim["template"],
            "role": claim.get("role"),
            "part": template_part(claim["template"]),  # AG8-D §4
            "status": claim["status"],
            "scope": [scope_text(s) for s in claim.get("effective_scopes", ())],
        }
        proves = claim_proves(claim, record["side"])
        if proves is not None:
            entry["proves"] = proves
        says = _cap(said.get(claim["id"]), SAYS_CAP, capped, f"says:{claim.get('ref')}")
        if says is not None:
            entry["says"] = says
        attributed = _attributed(claim)
        if attributed is not None:
            entry["attributed"] = attributed
        entry["findings"] = _without_positions(claim.get("findings", []), capped,
                                               f"findings:{claim.get('ref')}")  # fmt: skip
        claims.append(entry)
    label = record.get("label") or None
    kind = label.get("kind") if isinstance(label, dict) else label
    evaluation = record.get("evaluation") or {}
    played, best = subject.get("played"), subject.get("best")
    if best is not None and played is not None and best.get("rank") == played.get("rank"):
        best = None  # the played move is the best: its line is `played`
    taken = {line.get("rank") for line in (played, best) if line is not None}
    others = [
        {"ref": a.get("ref"), "move": a["move"]["san"], "score": a.get("score"),
         "score_text": score_text(a.get("score"))}
        for a in subject.get("alternatives", ()) if a.get("rank") not in taken
    ][:OTHERS]  # fmt: skip
    out = {
        "ply": record["ply"],
        "move": numbered(record["move_number"], record["side"], record["san"]),
        "side": record["side"],
        "status": record["status"],
        "grade": record.get("grade"),
        "grade_ko": glossary["grades"].get(record.get("grade")) if record.get("grade") else None,
        "label": kind,
        "label_ko": glossary["labels"].get(kind) if kind else None,
    }
    if isinstance(label, dict) and label.get("provisional"):
        out["label_provisional"] = True
    out |= {
        "fen_before": record["fen_before"],
        "fen_after": record["fen_after"],
        "evaluation": {
            "played": score_text(evaluation.get("played")),
            "best": score_text(evaluation.get("best")),
            "loss": evaluation.get("loss"),
            "best_move": (evaluation.get("best_move") or {}).get("san"),
        },
        "judgement": subject.get("ref"),
        "lines": {
            "played": _line(played, PV_PLIES),
            "best": _line(best, PV_PLIES),
            "others": others,
        },
        "text": _cap(record.get("text"), TEXT_CAP, capped, "text"),
    }
    shown = {name: [p["uci"] for p in (line.get("pv") or [])[:PV_PLIES]]
             for name, line in (("played", played), ("best", best)) if line is not None}  # fmt: skip
    for i, other in enumerate(
        o for o in subject.get("alternatives", ()) if o.get("rank") not in taken
    ):
        if i < OTHERS:
            shown[f"others.{i}"] = [other["move"]["uci"]]
    passing = en_passant(record["fen_before"], shown)
    if passing:
        out["en_passant"] = passing  # the SAN names the square the pawn goes to, not its capture
    out |= {
        "claims": claims,
        "refuted": refuted,
        "not_shown": {
            "observations": len(analysis.get("observations", ())),
            "behind_detail": list(BEHIND_DETAIL),
            "full": 'view: "full"',
            "named": [],
            "steps": [],
            "counts": {},
            "capped": capped,
        },
    }
    return out


def bounded(d: dict, limit: int = DIGEST_LIMIT) -> dict:
    """§3.6: the steps in order, each only while the digest is over `limit`; a digest still over
    after the last raises `DigestTooLarge`."""

    d = copy.deepcopy(d)
    hidden = d["not_shown"]

    def ran(step: str, count: int) -> None:
        hidden["steps"].append(step)
        hidden["counts"][step] = count

    if size(d) > limit:  # 0: board items beyond the kept ones (AG8-D §2.3)
        ran("board", 0)
        changes = d.get("board", {}).get("changes", [])
        for kind in ("threat", "weakness", "lost_defence"):
            mine = [i for i, c in enumerate(changes) if c["kind"] == kind]
            for index in reversed(mine[BOARD_KEEP[kind] :]):
                if size(d) <= limit:
                    break
                changes.pop(index)
                hidden["counts"]["board"] += 1
    if size(d) > limit:  # 1: findings behind `detail`, each claim keeping its count
        for claim in d["claims"]:
            claim["findings"] = len(claim.get("findings") or [])
        ran("findings", sum(c["findings"] for c in d["claims"]))  # the findings moved (review N1)
    if size(d) > limit:  # 2: PVs to 4 plies
        lines = [line for line in (d["lines"]["played"], d["lines"]["best"]) if line]
        for line in lines:
            line["pv"] = " ".join(line["pv"].split()[:PV_SHORT])
        ran("short_pv", len(lines))
    if size(d) > limit:  # 3: INCONCLUSIVE claims named only
        named = [c for c in d["claims"] if c["status"] == "inconclusive"]
        d["claims"] = [c for c in d["claims"] if c["status"] != "inconclusive"]
        hidden["named"] += [{"template": c["template"], "ref": c["ref"], "status": c["status"]}
                            for c in named]  # fmt: skip
        ran("inconclusive_named", len(named))
    if size(d) > limit and d.get("text") is not None:  # 4: the text (in view: "full")
        d.pop("text")
        ran("text", 1)
    # 5 and 6 run one item at a time: their bookkeeping is in place first, so each measure
    # counts it and the last one leaves the digest within the bound
    if size(d) > limit:  # 5: SUPPORTED claims named only, from the end, until it fits
        ran("supported_named", 0)
        while d["claims"] and size(d) > limit:
            c = d["claims"].pop()
            hidden["named"].insert(0, {"template": c["template"], "ref": c["ref"],
                                       "status": c["status"]})  # fmt: skip
            hidden["counts"]["supported_named"] += 1
    if size(d) > limit:  # 6: named entries left out, from the end (the REFUTED list first)
        ran("named_left_out", 0)
        hidden["left_out"] = 0
        while (d["refuted"] or hidden["named"]) and size(d) > limit:
            (d["refuted"] if d["refuted"] else hidden["named"]).pop()
            hidden["counts"]["named_left_out"] += 1
            hidden["left_out"] += 1
    if size(d) > limit:
        raise DigestTooLarge(f"the answer exceeds its size bound ({size(d)} > {limit}); read it "
                             'with view: "full" or detail')  # fmt: skip
    return d
