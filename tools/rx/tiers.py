"""WG-D §1–§3: a game's plies in three tiers, tier 1's batches and judged sample, and tier 0's
followed-line sentence. Pure functions over `game_overview`'s lines; the harness drives them."""

from __future__ import annotations

TIER1_GRADES = ("inaccuracy", "mistake", "blunder")
TIER1_LABELS = ("miss", "brilliant", "great")  # "forced" is tier 0: a forced move needs no comment
BATCH = 8  # WG-D §2: tier-1 plies a batch at most
SAMPLE = 3  # WG-D §5: the tier-1 plies a game a score row judges
FOLLOWED = 2  # WG-D §3: plies past the commented one the game must follow to say so


def tiers_of(lines: list[dict], fixed: list[int]) -> dict[int, int]:
    """Each ply's tier: 2 for the fixed moments, 1 for another graded error or labelled move, 0 for
    the rest (an unanalysed ply too)."""

    out = {}
    for line in lines:
        ply = line["ply"]
        if ply in fixed:
            out[ply] = 2
        elif line.get("grade") in TIER1_GRADES or line.get("label") in TIER1_LABELS:
            out[ply] = 1
        else:
            out[ply] = 0
    for ply in fixed:
        out[ply] = 2
    return out


def batches(plies: list[int], size: int = BATCH) -> list[list[int]]:
    """Tier 1's plies in ply order, `size` at most a batch."""

    ordered = sorted(plies)
    return [ordered[i : i + size] for i in range(0, len(ordered), size)]


def halves(batch: list[int]) -> list[list[int]]:
    """A batch whose first message is over its limit, cut in two (one ply stays one)."""

    if len(batch) < 2:
        return [batch]
    middle = (len(batch) + 1) // 2
    return [batch[:middle], batch[middle:]]


def sample(lines: list[dict], tiers: dict[int, int], k: int = SAMPLE) -> list[int]:
    """WG-D §5: the `k` tier-1 plies with the largest loss (the earlier on a tie), in ply order —
    the same plies in every run of the game, since the grades are the sealed base's."""

    loss = {line["ply"]: line.get("loss") or 0 for line in lines}
    tier1 = [p for p, t in tiers.items() if t == 1]
    chosen = sorted(tier1, key=lambda p: (-loss.get(p, 0), p))[:k]
    return sorted(chosen)


def follows(game: list[str], start: int, moves: list[str]) -> int:
    """How many of `moves` (UCI), played from ply `start` (1-based: the line's first move is the
    game's ply `start`), the game played exactly, from the line's first move on."""

    n = 0
    for i, uci in enumerate(moves):
        ply = start + i
        if ply > len(game) or game[ply - 1] != uci:
            break
        n += 1
    return n


def line_start(game: list[str], record: dict, after: int) -> tuple[int, list[str]] | None:
    """Where a cited line's record starts on the game's own line, and its moves (UCI):
    - an explored line (`x`): its `start.from_root` is the game's first moves, exactly;
    - an engine line (`s`): its PV's first move is the game's move at ply `after` (the played
      move's line) or `after + 1` (a line after the move).
    None when the line is not on the game's line."""

    start = record.get("start") if isinstance(record.get("start"), dict) else None
    if start is not None and isinstance(start.get("from_root"), list):
        root = list(start["from_root"])
        end = (
            (record.get("end") or {}).get("from_root")
            if isinstance(record.get("end"), dict)
            else None
        )
        if root != game[: len(root)] or not isinstance(end, list) or end[: len(root)] != root:
            return None
        return len(root) + 1, list(end[len(root) :])
    pv = [x.get("uci") for x in record.get("pv") or [] if isinstance(x, dict)]
    if not pv:
        return None
    for first in (after, after + 1):
        if 0 < first <= len(game) and game[first - 1] == pv[0]:
            return first, pv
    return None


def followed_sentence(game: list[str], sans: list[str], commented: int, tiers: dict[int, int],
                      lines: list[tuple[str, dict]]) -> dict | None:  # fmt: skip
    """WG-D §3: the first tier-0 ply after a commented ply where the game went on as a cited line,
    with its sentence; None when no cited line was followed `FOLLOWED` plies past the commented one.
    `lines`: (handle, record) of the commentary's cited lines; `sans`: the game's numbered moves."""

    best = None
    for ref, record in lines:
        placed = line_start(game, record, commented)
        if placed is None:
            continue
        first, moves = placed
        n = follows(game, first, moves)
        last = first + n - 1
        # review (slice 3 F2): the line's own moves are followed, from the commented ply or the
        # next one; moves on its way there (an explored line's `from_root`) count for nothing
        if n < 1 or first > commented + 1 or last - commented < FOLLOWED:
            continue
        if best is None or last > best["until"]:
            best = {"ref": ref, "from": first, "until": last}
    if best is None:
        return None
    quiet = [p for p in range(commented + 1, best["until"] + 1) if tiers.get(p) == 0]
    if not quiet:
        return None
    until = sans[best["until"] - 1]
    return {"ply": quiet[0], "from_ply": commented, "until_ply": best["until"], "ref": best["ref"],
            "text": f"앞서 본 수순대로 진행되었다 ({until}까지).", "source": "code"}  # fmt: skip
