"""The freeze record (RX0-D §2 step 1; LT implementation review N1): what a Test measurement fixed
before Test was opened — the model, each variant's tools, harness and server commit, and the bounds —
checked when Test is opened and again before every Test run, so a Test result is the frozen
candidate's and nothing else's.

```json
{"version": "freeze_v1", "model": "anthropic/claude-haiku-5.5",
 "commit": "<the repository's commit at the freeze, 40 hex>",
 "bounds": {"turns": 90, "tool_calls": 150, "tokens": 4000000},
 "variants": {
   "A@v7": {"tools": "agent_tools_v7", "commit": "<the v7 server root's commit>"},
   "H@v8": {"tools": "agent_tools_v8", "harness_revision": 5, "harness": "harness_v3",
            "harness_judge": "harness_judge_v2", "harness_sentences": "harness_sentences_v1"}}}
```
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

FREEZE_VERSION = "freeze_v1"
BOUND_KEYS = ("turns", "tool_calls", "tokens")
_COMMIT = re.compile(r"[0-9a-f]{40}")


def problems(doc) -> list[str]:
    """What makes a freeze record not one: the fields RX0-D §2 step 1 fixes, each well formed and
    each variant's versions those its tools and harness revision name."""

    from .harness import VERSIONS
    from .run import ARMS, HARNESS_ARMS, TOOLS_VERSIONS

    if not isinstance(doc, dict):
        return ["the freeze record is not a JSON object"]
    out = []
    if doc.get("version") != FREEZE_VERSION:
        out.append(f"version is not {FREEZE_VERSION}")
    if not isinstance(doc.get("model"), str) or not doc["model"]:
        out.append("no model")
    if not isinstance(doc.get("commit"), str) or not _COMMIT.fullmatch(doc["commit"]):
        out.append("commit is not a 40-hex commit")
    bounds = doc.get("bounds")
    if not isinstance(bounds, dict) or any(
        not isinstance(bounds.get(k), int) or isinstance(bounds.get(k), bool) or bounds[k] <= 0
        for k in BOUND_KEYS
    ):
        out.append(f"bounds must give {', '.join(BOUND_KEYS)} as positive integers")
    variants = doc.get("variants")
    if not isinstance(variants, dict) or not variants:
        return out + ["no variants"]
    for name, v in variants.items():
        arm, _, tools = str(name).partition("@")
        if arm not in ARMS or tools not in TOOLS_VERSIONS or not isinstance(v, dict):
            out.append(f"{name}: not a variant ARM@TOOLS with its record")
            continue
        if v.get("tools") != TOOLS_VERSIONS[tools]:
            out.append(f"{name}: tools is not {TOOLS_VERSIONS[tools]}")
        if "commit" in v and not (isinstance(v["commit"], str) and _COMMIT.fullmatch(v["commit"])):
            out.append(f"{name}: commit is not a 40-hex commit")
        if arm in HARNESS_ARMS:
            rev = v.get("harness_revision")
            if rev not in VERSIONS:
                out.append(f"{name}: no harness revision {rev!r}")
                continue
            messages, judge, sentences = VERSIONS[rev]
            want = {"harness": messages, "harness_judge": judge, "harness_sentences": sentences}
            for key, value in want.items():
                if value is not None and v.get(key) != value:
                    out.append(f"{name}: {key} is not {value} (revision {rev})")
    return out


def read(path: Path) -> tuple[dict | None, str]:
    """The record and its SHA-256; an unreadable file is None."""

    raw = path.read_bytes()
    try:
        doc = json.loads(raw)
    except ValueError:
        doc = None
    return doc, hashlib.sha256(raw).hexdigest()


def run_problems(opened: dict | None, spec) -> list[str]:
    """Before a Test run: Test is open, its freeze record unchanged, and the run is the frozen
    variant — its model, tools, harness revision and bounds."""

    if not opened:
        return ["Test is not open: open-test after the freeze (RX0-D §2)"]
    path = Path(opened["freeze"])
    if not path.is_file():
        return [f"the freeze record {path} is gone"]
    doc, digest = read(path)
    if digest != opened.get("freeze_sha256"):
        return ["the freeze record changed after Test was opened"]
    if doc is None:
        return ["the freeze record is not JSON"]
    name = f"{spec.arm}@{spec.tools}" if spec.tools else spec.arm
    frozen = (doc.get("variants") or {}).get(name)
    if frozen is None:
        return [f"{name} is not a frozen variant ({', '.join(doc.get('variants') or {})})"]
    out = []
    if spec.model != doc.get("model"):
        out.append(f"model {spec.model} is not the frozen {doc.get('model')}")
    for key in BOUND_KEYS:
        if getattr(spec.bounds, key) != (doc.get("bounds") or {}).get(key):
            out.append(f"bound {key} {getattr(spec.bounds, key)} is not the frozen "
                       f"{(doc.get('bounds') or {}).get(key)}")  # fmt: skip
    if "harness_revision" in frozen and spec.harness_revision != frozen["harness_revision"]:
        out.append(f"harness revision {spec.harness_revision} is not the frozen "
                   f"{frozen['harness_revision']}")  # fmt: skip
    return out
