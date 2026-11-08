"""A run's wholeness (RX0-D §4.4, RX1-D §8) and each moment-run's final commentary (RX0-D §6.0)."""

from __future__ import annotations

import json
from pathlib import Path


def lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            out.append(json.loads(raw))
    return out


def check(run_dir: Path, runner: bool = True) -> dict:
    """Whole: each required layer has `start` and `end` and no gap in `seq`; for the runner, every
    model tool call has its `call` line, in order, and every event names its call."""

    tools = lines(run_dir / "tools.jsonl")
    agent = lines(run_dir / "agent.jsonl")
    problems = []
    layers = [("tools", tools)] + ([("agent", agent)] if runner else [])
    for name, layer in layers:
        if not layer:
            problems.append(f"{name}: no lines")
            continue
        if layer[0].get("type") != "start":
            problems.append(f"{name}: no start")
        if layer[-1].get("type") != "end":
            problems.append(f"{name}: no end")
        seqs = [line["seq"] for line in layer]
        if seqs != list(range(1, len(seqs) + 1)):
            problems.append(f"{name}: a gap in seq")
    calls = [line for line in tools if line.get("type") == "call"]
    if runner:
        # every tool call the model asked for, less those the runner did not send (a call whose
        # arguments were not a JSON object, calls past the bound), one for one with the server's
        unsent = [line["tool_call_id"] for line in agent if line.get("type") == "tool_unsent"]
        # LT-D §5.2: the harness's own `detail` calls (`harness_call`) are in the server's lines
        # too, in their place among the agent's
        asked = []
        for line in agent:
            if line.get("type") == "response":
                asked += [(c.get("id"), c["function"]["name"])
                          for c in line["message"].get("tool_calls") or []]  # fmt: skip
            elif line.get("type") == "harness_call":
                asked.append((None, line["tool"]))
        for cid in unsent:
            hit = next((i for i, (aid, _) in enumerate(asked) if aid == cid), None)
            if hit is not None:
                asked.pop(hit)
        made = [line for line in agent if line.get("type") == "response"]
        if [c["tool"] for c in calls] != [name for _, name in asked]:
            problems.append(f"tool calls: the agent sent {len(asked)}, the server has {len(calls)}")
    ids = {c["call_id"] for c in calls}
    seen_call = set()
    for line in tools:
        if line.get("type") == "call":
            seen_call.add(line["call_id"])
        elif line.get("type") in ("handle", "submission"):
            cid = line.get("call_id")
            if cid is not None and (cid not in ids or cid not in seen_call):
                problems.append(
                    f"seq {line['seq']}: {line['type']} before or without its call {cid}"
                )
    end = tools[-1] if tools and tools[-1].get("type") == "end" else {}
    return {"whole": not problems, "problems": problems, "calls": len(calls),
            "capped": end.get("capped_calls", []),
            "agent_end": agent[-1].get("reason") if agent and agent[-1].get("type") == "end" else None,
            "responses": len(made) if runner else None}  # fmt: skip


def evidence(run_dir: Path) -> dict[str, dict]:
    """Every handle the run served: its `identity`, and its `line_key` when it is a line."""

    return {
        line["ref"]: {"identity": line["identity"], "line_key": line.get("line_key")}
        for line in lines(run_dir / "tools.jsonl")
        if line.get("type") == "handle"
    }


def cites(sentences: list[dict] | None) -> set[str]:
    return {c for s in sentences or [] for c in s.get("cites") or [] if isinstance(c, str)}


def covered(cited: set[str], served: dict[str, dict], cause: list[dict]) -> bool:
    """RX0-D §6.2 M2a: a key cause is covered when a cited handle is one of its items, by
    `identity`, or, for an item named by `line_key`, a cited line of either source with that key."""

    for ref in cited:
        known = served.get(ref.split(":", 1)[0])
        if known is None:
            continue
        for item in cause:
            if item.get("identity") and item["identity"] == known["identity"]:
                return True
            if item.get("line_key") and item["line_key"] == known.get("line_key"):
                return True
    return False


def finals(run_dir: Path, moments: list[int]) -> dict[int, dict | None]:
    """RX0-D §6.0: per fixed moment, the last `accepted` or `duplicate` submission of the run for
    that ply (its sentences as the agent sent them), or None. A subject counts by `game_ply`, its
    path on the game's own line, however it was named (`ply`, or `position` and `move`); a move
    not played has none and never stands for the played ply of the same number (review B3)."""

    out: dict[int, dict | None] = {p: None for p in moments}
    for line in lines(run_dir / "tools.jsonl"):
        if line.get("type") != "submission":
            continue
        for subject in line["subjects"]:
            ply = subject.get("game_ply")
            if ply in out and subject.get("outcome") in ("accepted", "duplicate"):
                out[ply] = {"seq": line["seq"], "call_id": line.get("call_id"),
                            "outcome": subject["outcome"], "id": subject.get("id"),
                            "sentences": (subject.get("submitted") or {}).get("sentences")}  # fmt: skip
    return out
