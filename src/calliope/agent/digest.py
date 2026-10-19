"""The digest of a ply (AG6-D §3): what an agent writes from or cites, the rest one call away.

`ply` and `judge_move` answer it by default; `view: "full"` keeps today's answer. Every item the
full answer serves keeps its handle (served by the session, whether or not the digest shows it),
so verification reads the served item, never the digest (V2). REFUTED claims are named and the
observations counted (V3); bundle digests, curves, policies, search ids and segments are never
shown (V4); a position is given once and a line as SAN (V5). The digest is bounded (§3.6): fields
of free length are capped, then fixed steps move items behind `detail` until it fits, and
`not_shown` says what moved. Moves shown as strings carry their numbers (PW-D §2).
"""

from __future__ import annotations

import copy
import json
from decimal import ROUND_HALF_UP, Decimal

from .remarks import claim_proves, en_passant, template_part

DIGEST_LIMIT = 16_000  # characters of the compact JSON `content` (§3.6)
FINDING_CAP = 100
PV_PLIES = 8
PV_SHORT = 4  # step 2
OTHERS = 3  # candidates beyond the played and the best move
ROLE_ORDER = ("consequence", "comparison", "mechanism", "function")
MATERIAL_TEMPLATES = ("material_gain_v3", "material_loss_v2")  # the templates with ATTRIBUTED
POSITION_KEYS = frozenset({"node", "from_root", "fen", "position", "target", "line", "lines"})
BEHIND_DETAIL = ("scopes in full", "evidence", "relations", "checks", "PVs beyond the digest's",
                 "the other candidates", "the REFUTED claims", "a claim's findings (with proves)",
                 "Calliope's text and the claims' sentences (view: full)")  # fmt: skip
STEPS = ("board", "also", "findings", "short_pv", "inconclusive_named", "supported_named")
BOARD_KEEP = {"threat": 2, "weakness": 0, "held": 0, "lost_defence": 2}  # AG8-D §2.3; MS-D §6
WEAK = ("inaccuracy", "mistake", "blunder")  # `board.WEAK_GRADES` (BL-D §5)
# MS-D §7: groups of claims shown once — the members by what they name
GROUPS = (("better_move_v1", "missed_gain_v1", "better_alternative_v1"),
          ("piece_offer_v1", "sacrifice_offer_v1"),
          ("mate_allowed_v1", "mate_in_one_allowed_v1"))  # fmt: skip


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


def numbered_line(fen: str, sans: list[str]) -> str:
    """PW-D §2: a line's moves from `fen` as in PGN — `15.f5 Qxd4 16.Ne2`, `15...Qxb2 16.O-O` —
    one token a move."""

    fields = fen.split()
    try:
        white, number = fields[1] == "w", int(fields[5])
    except (IndexError, ValueError):
        return " ".join(sans)  # not a position (a record made by hand), as `en_passant` reads it
    out = []
    for index, san in enumerate(sans):
        if white:
            out.append(f"{number}.{san}")
        else:
            out.append(f"{number}...{san}" if index == 0 else san)
            number += 1
        white = not white
    return " ".join(out)


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


def _line(line: dict | None, plies: int, fen: str) -> dict | None:
    if line is None:
        return None
    return {
        "ref": line.get("ref"),
        "move": numbered_line(fen, [line["move"]["san"]]),
        "score": line.get("score"),
        "score_text": score_text(line.get("score")),
        "depth": line.get("depth"),
        "pv": numbered_line(fen, [p["san"] for p in (line.get("pv") or [])[:plies]]),
    }


def _numbered_san(record: dict, san: str | None) -> str | None:
    """A move at the ply's position (its best move), numbered as the ply's move is."""

    return None if san is None else numbered(record["move_number"], record["side"], san)


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


def digest(record: dict, glossary: dict) -> dict:
    """The digest of a full `ply` / `judge_move` record whose items carry their refs (§3.2), with
    MS-D §7–§8: a claim's `proves` in place of its sentence and findings, the groups shown once,
    the REFUTED claims and the other candidates by their refs in `not_shown`."""

    capped: dict[str, int] = {}
    analysis = record["analysis"]
    subject = analysis["judgements"][0]
    claims, refuted = [], []
    ordered = sorted(enumerate(analysis["claims"]), key=lambda pair: (_role_rank(pair[1]), pair[0]))
    for _, claim in ordered:
        if claim["status"] == "refuted":
            refuted.append(claim.get("ref"))
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
            entry["proves"] = proves  # MS-D §8: in place of `says` and of the findings
        attributed = _attributed(claim)
        if attributed is not None:
            entry["attributed"] = attributed
        if proves is None:  # a claim whose findings lack what its `proves` needs keeps them
            entry["findings"] = _without_positions(claim.get("findings", []), capped,
                                                   f"findings:{claim.get('ref')}")  # fmt: skip
        claims.append(entry)
    claims = grouped(claims)
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
            "best_move": _numbered_san(record, (evaluation.get("best_move") or {}).get("san")),
        },
        "judgement": subject.get("ref"),
        "lines": {
            "played": _line(played, PV_PLIES, record["fen_before"]),
            "best": _line(best, PV_PLIES, record["fen_before"]),
        },
    }
    shown = {name: [p["uci"] for p in (line.get("pv") or [])[:PV_PLIES]]
             for name, line in (("played", played), ("best", best)) if line is not None}  # fmt: skip
    passing = en_passant(record["fen_before"], shown)
    if passing:
        out["en_passant"] = passing  # the SAN names the square the pawn goes to, not its capture
    out |= {
        "claims": claims,
        "not_shown": {  # MS-D §8.1: behind `detail` by these refs, and in `view: "full"`
            "refuted": refuted,
            "others": [o["ref"] for o in others],
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


def grouped(claims: list[dict]) -> list[dict]:
    """MS-D §7 (review B5): of a group's members present, the first SUPPORTED one by what it names
    is shown, else the first INCONCLUSIVE one; the others go under it as `also`, with their
    status."""

    out = list(claims)
    for group in GROUPS:
        members = [c for t in group for c in out if c["template"] == t]
        if len(members) < 2:
            continue
        shown = next((c for c in members if c["status"] == "supported"), members[0])
        rest = [c for c in members if c is not shown]
        shown["also"] = [{"ref": c["ref"], "template": c["template"], "status": c["status"],
                          **({"proves": c["proves"]} if "proves" in c else {})}
                         for c in rest]  # fmt: skip
        out = [c for c in out if not any(c is x for x in rest)]
    return out


def settle(built: dict, d: dict) -> None:
    """MS-D §6 (review B4): one relation once, on what the bound left. A claim leaves `claims`
    only when the board item carrying its `leads_to` is shown; a linked item the bound moved out is
    named in `not_shown` with its claim, which stays listed."""

    shown = {c["ref"] for c in d.get("board", {}).get("changes", []) if "ref" in c}
    gone_claims = set()
    for item in built.get("changes", []):
        leads = item.get("leads_to")
        if not leads or not leads.get("claim"):
            continue
        if item.get("ref") in shown:
            gone_claims.add(leads["claim"])
        else:
            d["not_shown"]["named"].append({"board": item["kind"], "ref": item.get("ref"),
                                            "leads_to": leads["claim"]})  # fmt: skip
    d["claims"] = [c for c in d.get("claims", []) if c.get("ref") not in gone_claims]


def bounded(d: dict, limit: int = DIGEST_LIMIT, built: dict | None = None) -> dict:
    """§3.6: the steps in order, each only while the digest is over `limit`; a digest still over
    after the last raises `DigestTooLarge`. With `built` (the board as built), each measure is of
    the digest as `settle` leaves it, and the digest returned is settled (MS-b review B2). No
    step drops a handle: what leaves the digest is named by its ref (MS-D I4, review B3)."""

    d = copy.deepcopy(d)
    hidden = d["not_shown"]

    def measured() -> int:
        if built is None:
            return size(d)
        trial = copy.deepcopy(d)
        settle(built, trial)
        return size(trial)

    def ran(step: str, count: int) -> None:
        hidden["steps"].append(step)
        hidden["counts"][step] = count

    if measured() > limit:  # 0: board items beyond the kept ones (AG8-D §2.3)
        ran("board", 0)
        changes = d.get("board", {}).get("changes", [])
        # BL-D §5 (2): on a weak move the first item (the largest stake) and the item threats
        # point at are kept whatever their kinds; the counts apply to the rest
        firsts = {c.get("opponent_first") for c in changes} - {None}
        guarded = [c for i, c in enumerate(changes)
                   if (i == 0 and d.get("grade") in WEAK) or c.get("ref") in firsts]  # fmt: skip
        for kind in ("threat", "weakness", "held", "lost_defence"):
            mine = [i for i, c in enumerate(changes)
                    if c["kind"] == kind and not any(c is g for g in guarded)]  # fmt: skip
            # MS-D §6: an item with `leads_to` (and a `held` one) is kept before the others
            linked = [i for i in mine if "leads_to" in changes[i]]
            plain = [i for i in mine if "leads_to" not in changes[i]]
            beyond = [changes[i] for i in (linked + plain)[BOARD_KEEP[kind] :]]
            # the plain ones first, from the end; then the linked ones, from the end
            for item in sorted(beyond, key=lambda c: ("leads_to" in c, -changes.index(c))):
                if measured() <= limit:
                    break
                changes[:] = [c for c in changes if c is not item]
                hidden["counts"]["board"] += 1
    if measured() > limit:  # 0b: a group's other members by their refs (MS-D §10)
        moved = 0
        for claim in d["claims"]:
            for other in claim.pop("also", []):
                hidden["named"].append({"template": other["template"], "ref": other["ref"],
                                        "status": other["status"]})  # fmt: skip
                moved += 1
        ran("also", moved)
    if measured() > limit:  # 1: findings behind `detail`, each claim keeping its count
        for claim in d["claims"]:
            if "findings" in claim:  # MS-D §10: only where still shown
                claim["findings"] = len(claim.get("findings") or [])
        ran("findings", sum(c.get("findings", 0) for c in d["claims"]))  # review N1
    if measured() > limit:  # 2: PVs to 4 plies
        lines = [line for line in (d["lines"]["played"], d["lines"]["best"]) if line]
        for line in lines:
            line["pv"] = " ".join(line["pv"].split()[:PV_SHORT])
        ran("short_pv", len(lines))
    if measured() > limit:  # 3: INCONCLUSIVE claims named only
        named = [c for c in d["claims"] if c["status"] == "inconclusive"]
        d["claims"] = [c for c in d["claims"] if c["status"] != "inconclusive"]
        hidden["named"] += [{"template": c["template"], "ref": c["ref"], "status": c["status"]}
                            for c in named]  # fmt: skip
        ran("inconclusive_named", len(named))
    # 5 runs one item at a time: its bookkeeping is in place first, so each measure counts it
    if measured() > limit:  # 5: SUPPORTED claims named only, from the end, until it fits
        ran("supported_named", 0)
        while d["claims"] and measured() > limit:
            c = d["claims"].pop()
            hidden["named"].insert(0, {"template": c["template"], "ref": c["ref"],
                                       "status": c["status"]})  # fmt: skip
            hidden["counts"]["supported_named"] += 1
    if built is not None:
        settle(built, d)
    if size(d) > limit:  # every handle still named: an error, never a cut (MS-D I4)
        raise DigestTooLarge(f"the answer exceeds its size bound ({size(d)} > {limit}); read it "
                             'with view: "full" or detail')  # fmt: skip
    return d
