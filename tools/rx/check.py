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
        asked = [c["function"]["name"] for line in agent if line.get("type") == "response"
                 for c in line["message"].get("tool_calls") or []]  # fmt: skip
        # a call whose arguments were not a JSON object never reached the server
        made = [line for line in agent if line.get("type") == "response"]
        if [c["tool"] for c in calls] != asked[: len(calls)] or len(calls) > len(asked):
            problems.append(
                f"tool calls: the agent asked {len(asked)}, the server has {len(calls)}"
            )
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


def finals(run_dir: Path, moments: list[int]) -> dict[int, dict | None]:
    """RX0-D §6.0: per fixed moment, the last `accepted` or `duplicate` submission of the run for
    that ply (its sentences as the agent sent them), or None."""

    out: dict[int, dict | None] = {p: None for p in moments}
    for line in lines(run_dir / "tools.jsonl"):
        if line.get("type") != "submission":
            continue
        for subject in line["subjects"]:
            ply = (subject.get("subject") or {}).get("ply")
            if ply in out and subject.get("outcome") in ("accepted", "duplicate"):
                out[ply] = {"seq": line["seq"], "call_id": line.get("call_id"),
                            "outcome": subject["outcome"], "id": subject.get("id"),
                            "sentences": (subject.get("submitted") or {}).get("sentences")}  # fmt: skip
    return out
