"""`schema_errors`: the shipped schema without `jsonschema` (AS1 re-review B3).

Its verdicts are compared with `jsonschema` on every corpus document and on thousands of broken
ones: every field deleted, nulled, retyped or emptied, in turn.
"""

from __future__ import annotations

import copy
import json

import jsonschema
import pytest
from corpus_case import cases
from test_result import corpus_result

from calliope.results import ResultError, schema, schema_errors
from calliope.results import validate as validate_module

VALIDATOR = jsonschema.Draft202012Validator(schema())
DOCS = {case["name"]: corpus_result(case)[1] for case in cases()}


def _paths(value, path=()):
    yield path
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _paths(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _paths(item, (*path, index))


def _replacements(value):
    """Wrong values for a field: absent, null, another type, empty, out of range."""

    yield "delete"
    yield None
    yield {} if not isinstance(value, dict) else []
    yield "x" if not isinstance(value, str) else 7
    if isinstance(value, str):
        yield ""
    if isinstance(value, bool):
        yield 1
    elif isinstance(value, int):
        yield -1
        yield 1.5
        yield True
    if isinstance(value, list):
        yield []


def _mutants(doc):
    for path in _paths(doc):
        if not path:
            continue
        parent_path, key = path[:-1], path[-1]
        original = doc
        for part in path:
            original = original[part]
        for replacement in _replacements(original):
            mutant = copy.deepcopy(doc)
            parent = mutant
            for part in parent_path:
                parent = parent[part]
            if replacement == "delete":
                if isinstance(parent, dict):
                    del parent[key]
                else:
                    del parent[key]
            else:
                parent[key] = replacement
            yield path, replacement, mutant


@pytest.mark.parametrize("name", sorted(DOCS))
def test_every_corpus_document_is_valid(name) -> None:
    assert schema_errors(DOCS[name]) == [] and VALIDATOR.is_valid(DOCS[name])


@pytest.mark.parametrize("name", sorted(DOCS))
def test_the_verdicts_agree_with_jsonschema_on_every_mutation(name) -> None:
    doc = DOCS[name]
    checked = rejected = 0
    for path, replacement, mutant in _mutants(doc):
        ours, theirs = not schema_errors(mutant), VALIDATOR.is_valid(mutant)
        assert ours == theirs, (path, replacement)
        checked += 1
        rejected += not ours
    assert checked > 300 and rejected > checked // 2


@pytest.mark.parametrize(
    "path",
    [
        ("plies", 0, "text"),
        ("plies", 0, "segments"),
        ("plies", 0, "claims"),
        ("plies", 0, "evaluation"),
        ("plies", 0, "segments", 0, "refs"),
        ("provenance", "build_digest"),
        ("grading",),
        ("summary",),
    ],
)
def test_a_missing_required_field_is_an_error(path) -> None:
    """The re-review's examples: `text`, `segments`, `claims`, the evaluation, and more."""

    doc = copy.deepcopy(DOCS["fork_blunder"])
    parent = doc
    for part in path[:-1]:
        parent = parent[part]
    del parent[path[-1]]
    assert schema_errors(doc) and not VALIDATOR.is_valid(doc)


@pytest.mark.parametrize("digest", ["zz", "A" * 64, "0" * 63, 7])
def test_a_wrong_bundle_digest_is_an_error(digest) -> None:
    doc = copy.deepcopy(DOCS["fork_blunder"])
    doc["plies"][0]["bundle"] = {"tree": digest, "graph": "0" * 64, "stored": True}
    assert schema_errors(doc) and not VALIDATOR.is_valid(doc)


def test_an_unknown_extra_field_is_still_valid() -> None:
    """AR-D G7: objects allow additional properties."""

    doc = copy.deepcopy(DOCS["fork_blunder"])
    doc["plies"][0]["later"] = {"anything": 1}
    assert schema_errors(doc) == [] and VALIDATOR.is_valid(doc)


def test_an_unsupported_keyword_fails_loudly(monkeypatch) -> None:
    grown = json.loads(json.dumps(schema()))
    grown["properties"]["schema"]["maxLength"] = 40
    monkeypatch.setattr(validate_module, "schema", lambda: grown)
    with pytest.raises(ResultError, match="unsupported keywords"):
        schema_errors(DOCS["fork_blunder"])
