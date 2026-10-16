"""The agent build (AG-D §10), the prompt texts and the registries as the server serves them.

Free of the MCP SDK, so the session can record the build with every accepted commentary.
"""

from __future__ import annotations

import hashlib
from importlib import resources

from calliope.facts import definitions_json
from calliope.reasoning import DEFINITIONS, REGISTRY_DIGEST

from .definitions import AGENT_DEFINITIONS, AGENT_DIGEST, GUIDANCE_VERSION, TOOLS_VERSION
from .definitions import as_json as agent_json
from .definitions import document as agent_document

PROMPTS = ("commentary_ko_v1", "check_ko_v1")


def text(name: str) -> str:
    return resources.files("calliope.agent.prompts").joinpath(name).read_text(encoding="utf-8")


def guide(name: str) -> str:
    """A prompt's text as a resource (AG5-D §4): the same file, its target `<game>` / `<ply>`."""

    return text(f"{name}.md").format(game="<game>", ply="<ply>")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def agent_build(reasoning_build: str | None = None) -> dict:
    """AG-D §10: the digests under which a commentary is accepted."""

    return {
        "agent_definitions": AGENT_DIGEST,
        "prompts": {name: sha(text(f"{name}.md")) for name in PROMPTS},
        "glossary": sha(text("glossary_ko_v1.json")),
        "tools": TOOLS_VERSION,
        "guidance": GUIDANCE_VERSION,
        "reasoning_build": reasoning_build,
    }


def definitions_document() -> dict:
    return {
        "definitions_v1": {
            "format": "definitions_v1",
            "digest": REGISTRY_DIGEST,
            "definitions": definitions_json(DEFINITIONS),
        },
        "agent_definitions_v1": agent_document(),
    }


def find_definitions(ids=None, kind=None, query=None, limit: int = 40) -> dict:
    entries = [*definitions_json(DEFINITIONS), *agent_json(AGENT_DEFINITIONS)]
    if ids:
        wanted = set(ids)
        found = [e for e in entries if e["id"] in wanted]
        missing = sorted(wanted - {e["id"] for e in found})
        return {"definitions": found, "missing": missing}
    kinds = sorted({e["kind"] for e in entries})
    if kind:
        entries = [e for e in entries if e["kind"] == kind]
    if query:
        words = query.lower().split()
        if len(words) > 1:  # every word, in the id, the statement or the field names (AG5-D §5.1)
            entries = [e for e in entries if all(w in _searched(e) for w in words)]
        else:
            q = query.lower()
            entries = [e for e in entries if q in e["id"].lower() or q in e["statement"].lower()]
    answer = {"definitions": entries[:limit], "total": len(entries), "limit": limit}
    if kind and kind not in kinds:  # say which kinds there are (AG5-D §5.1)
        answer["kinds"] = kinds
    return answer


def _searched(entry: dict) -> str:
    fields = [f for f in entry.get("fields", ()) if isinstance(f, str)]
    return " ".join([entry["id"], entry["statement"], *fields]).lower()
