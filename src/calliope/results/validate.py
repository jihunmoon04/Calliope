"""The shipped JSON Schema, checked without a runtime dependency (AS1 re-review B3).

`schema_errors(document)` validates a `calliope_result_v1` document against
`results/schema/calliope_result_v1.json` itself. It implements exactly the keywords that schema
uses (JSON Schema 2020-12 semantics); any other keyword raises `ResultError`, so a schema that
grows a new keyword fails loudly instead of being half-checked. The tests compare its verdicts
with `jsonschema` on valid documents and on many broken ones.
"""

from __future__ import annotations

import re
from functools import cache

from calliope.results.document import ResultError, schema

ANNOTATIONS = frozenset({"$schema", "$id", "title", "description", "$defs"})
KEYWORDS = frozenset(
    {
        "type", "required", "properties", "additionalProperties", "items", "const", "enum",
        "$ref", "minLength", "minimum", "minItems", "maxItems", "pattern", "allOf", "anyOf",
        "oneOf", "not", "if", "then", "else",
    }
)  # fmt: skip


def _is_type(value, kind: str) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    if kind == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (
            isinstance(value, float) and value.is_integer()
        )
    if kind == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    raise ResultError(f"schema: unknown type {kind!r}")


def _equal(a, b) -> bool:
    """JSON equality: booleans are not numbers, 1 equals 1.0."""

    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, int | float) and isinstance(b, int | float):
        return a == b
    return type(a) is type(b) and a == b


@cache
def _pattern(text: str) -> re.Pattern:
    return re.compile(text)


class _Validator:
    def __init__(self, root: dict) -> None:
        self.root = root

    def resolve(self, ref: str) -> dict:
        if not ref.startswith("#/"):
            raise ResultError(f"schema: only local references are supported, not {ref!r}")
        node = self.root
        for part in ref[2:].split("/"):
            node = node[part]
        return node

    def errors(self, value, node, path: str) -> list[str]:
        if node is True:
            return []
        if node is False:
            return [f"{path}: not allowed"]
        unknown = set(node) - KEYWORDS - ANNOTATIONS
        if unknown:
            raise ResultError(f"schema: unsupported keywords {sorted(unknown)} at {path}")
        out: list[str] = []
        if "$ref" in node:
            out += self.errors(value, self.resolve(node["$ref"]), path)
        if "type" in node:
            kinds = node["type"] if isinstance(node["type"], list) else [node["type"]]
            if not any(_is_type(value, k) for k in kinds):
                return out + [f"{path}: not of type {node['type']}"]
        if "const" in node and not _equal(value, node["const"]):
            out.append(f"{path}: not {node['const']!r}")
        if "enum" in node and not any(_equal(value, e) for e in node["enum"]):
            out.append(f"{path}: not one of {node['enum']!r}")
        if isinstance(value, str):
            if "minLength" in node and len(value) < node["minLength"]:
                out.append(f"{path}: shorter than {node['minLength']}")
            if "pattern" in node and not _pattern(node["pattern"]).search(value):
                out.append(f"{path}: does not match {node['pattern']!r}")
        if _is_type(value, "number") and "minimum" in node and value < node["minimum"]:
            out.append(f"{path}: below {node['minimum']}")
        if isinstance(value, list):
            if "minItems" in node and len(value) < node["minItems"]:
                out.append(f"{path}: fewer than {node['minItems']} items")
            if "maxItems" in node and len(value) > node["maxItems"]:
                out.append(f"{path}: more than {node['maxItems']} items")
            if "items" in node:
                for i, item in enumerate(value):
                    out += self.errors(item, node["items"], f"{path}[{i}]")
        if isinstance(value, dict):
            for name in node.get("required", ()):
                if name not in value:
                    out.append(f"{path}: missing {name!r}")
            properties = node.get("properties", {})
            for name, item in value.items():
                if name in properties:
                    out += self.errors(item, properties[name], f"{path}.{name}")
                elif "additionalProperties" in node:
                    out += self.errors(item, node["additionalProperties"], f"{path}.{name}")
        for sub in node.get("allOf", ()):
            out += self.errors(value, sub, path)
        if "anyOf" in node and not any(not self.errors(value, s, path) for s in node["anyOf"]):
            out.append(f"{path}: matches none of anyOf")
        if "oneOf" in node:
            matched = sum(1 for s in node["oneOf"] if not self.errors(value, s, path))
            if matched != 1:
                out.append(f"{path}: matches {matched} of oneOf, not exactly one")
        if "not" in node and not self.errors(value, node["not"], path):
            out.append(f"{path}: matches a forbidden schema")
        if "if" in node:
            branch = "then" if not self.errors(value, node["if"], path) else "else"
            if branch in node:
                out += self.errors(value, node[branch], path)
        return out


def schema_errors(document) -> list[str]:
    """Every violation of the shipped `calliope_result_v1` schema; empty when valid."""

    root = schema()
    return _Validator(root).errors(document, root, "$")
