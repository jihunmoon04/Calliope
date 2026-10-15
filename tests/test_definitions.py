"""DF-D §7 tests 1, 2, 5, 6: the definitions registry is complete, one value table, closed reason
codes, and the registry in the build."""

from __future__ import annotations

import ast
import dataclasses
import re
from enum import Enum
from pathlib import Path

import pytest

from calliope.facts import (
    FACT_REASONS,
    FactEngine,
    InputLine,
    NotApplicable,
    NotComputed,
    OpenRequest,
    RootSpec,
    definitions_json,
)
from calliope.facts import storage as fact_storage
from calliope.facts.families import REGISTRY as FAMILIES
from calliope.reasoning import FINDING_KINDS, Reasoner
from calliope.reasoning import build as build_module
from calliope.reasoning import definitions as R
from calliope.reasoning.catalogue import CATALOGUE_V1
from calliope.reasoning.hypotheses import Basis, PopulationKind, Quantifier, RelationKind
from calliope.reasoning.storage import REFUSALS
from calliope.reasoning.verification import REASONS, VerdictStatus

SRC = Path(__file__).resolve().parents[1] / "src" / "calliope"
IDS = {d.id: d for d in R.DEFINITIONS}

# -- 1. completeness -------------------------------------------------------------------------------


def test_every_field_of_every_record_type_is_stated() -> None:
    """DF-D §7 test 1 (DF1 review B1): the closed type registry, every record type of every
    family — fields of the dataclasses, and each enum as one entry naming its values."""

    missing = []
    for family in FAMILIES:
        assert family.version in IDS, family.version
        for kind in family.record_types:
            if dataclasses.is_dataclass(kind):
                missing += [
                    f"{family.version}.{kind.__name__}.{f.name}"
                    for f in dataclasses.fields(kind)
                    if f"{family.version}.{kind.__name__}.{f.name}" not in IDS
                ]
            else:
                key = f"{family.version}.{kind.__name__}"
                if key not in IDS:
                    missing.append(key)
                    continue
                statement = IDS[key].statement
                missing += [f"{key}: {m.value}" for m in kind if m.value not in statement]
    assert missing == []
    assert all(IDS[f"patterns_v1.PatternsFacts.{f}"].configuration_only for f in (
        "skewers", "relative_pins", "multi_target_attacks", "sole_defenders", "back_ranks"))  # fmt: skip


def test_templates_policies_rules_findings_and_vocabularies_are_stated() -> None:
    for t in CATALOGUE_V1:
        assert IDS[t.name].kind == "template", t.name
    for policy in (*build_module.POLICIES, "see_v1", "exposed_v1", "concession_v1", "points_v1"):
        assert policy in IDS, policy
    for rule in build_module.LABEL_RULES:
        assert IDS[rule].kind == "label_rule", rule
    for kind in FINDING_KINDS:
        if dataclasses.is_dataclass(kind):
            assert f"finding.{kind.__name__}" in IDS, kind.__name__
    assert {s.name for s in VerdictStatus} <= IDS.keys()
    assert {q.value for q in Quantifier} <= IDS.keys()
    assert {f"population.{p.value}" for p in PopulationKind} <= IDS.keys()
    assert {f"basis.{b.value}" for b in Basis} <= IDS.keys()
    assert {r.value for r in RelationKind} <= IDS.keys()
    assert {"REALIZED", "COUNTERFACTUAL", "ATTRIBUTED"} <= IDS.keys()


def test_every_unit_and_dependency_names_an_entry() -> None:
    for d in R.DEFINITIONS:
        if d.unit is not None:
            assert f"unit.{d.unit}" in IDS, (d.id, d.unit)
        for dep in d.depends_on:
            assert dep in IDS, (d.id, dep)
    for d in R.TEMPLATES:  # an entry names something that exists
        assert d.id in {t.name for t in CATALOGUE_V1}


MODULES = ("lines.py", "labels.py", "planner.py", "observer.py", "render/__init__.py",
           *(p.name and f"catalogue/{p.name}" for p in (SRC / "reasoning/catalogue").glob("*.py")))  # fmt: skip
EXEMPT = {"VERSION"}  # catalogue/base: the template version string


def _int_constants(path: Path) -> set[str]:
    out = set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            numeric = isinstance(value, ast.Constant) and type(value.value) is int
            numeric = numeric or (
                isinstance(value, ast.UnaryOp) and isinstance(value.operand, ast.Constant)
            )
            for t in targets:
                if isinstance(t, ast.Name) and t.id.isupper() and numeric:
                    out.add(t.id)
            if isinstance(value, ast.Tuple) and any(
                isinstance(t, ast.Name) and t.id == "BANDS" for t in targets
            ):
                out.add("BANDS")
    return out


def test_every_numeric_constant_of_the_reasoning_rules_is_a_threshold() -> None:
    names = {d.id for d in R.THRESHOLDS}
    for module in MODULES:
        for constant in _int_constants(SRC / "reasoning" / module) - EXEMPT:
            if constant == "BANDS":
                assert any(n.startswith("BANDS.") for n in names)
                continue
            assert constant in names, f"{module}: {constant} has no registry entry"


def test_threshold_values_are_the_codes_and_the_label_parameters_agree() -> None:
    from calliope.reasoning import labels
    from calliope.reasoning.catalogue import exchange, material

    values = {d.id: d.value for d in R.THRESHOLDS}
    assert values["GAIN_CP_PER_POINT"] == material.GAIN_CP_PER_POINT
    assert values["MISS_LOSS"] == labels.MISS_LOSS and values["NOT_BAD"] == exchange.NOT_BAD
    params = dict(build_module._label_parameters())
    names = {"brilliant_p2": ("OFFER_MIN", "NEAR_BEST", "NOT_BAD", "WINNING"),
             "miss_p2": ("MISS_OPPORTUNITY", "MISS_LOSS")}  # fmt: skip
    for rule, ids in names.items():
        assert tuple(values[i] for i in ids) == params[rule]


def test_the_registry_exports_as_definitions_v1() -> None:
    import json

    from tools.definitions.__main__ import document

    doc = json.loads(json.dumps(document()))
    assert doc["format"] == "definitions_v1" and doc["digest"] == R.REGISTRY_DIGEST
    assert [d["id"] for d in doc["definitions"]] == sorted(IDS)
    assert definitions_json(R.DEFINITIONS) == doc["definitions"]


# -- 2. one value table ----------------------------------------------------------------------------


def test_no_module_outside_the_fact_engine_defines_piece_values() -> None:
    pattern = re.compile(r'"(pawn|knight|bishop|rook|queen)"\s*:\s*\d|PieceType\.\w+\s*:\s*\d')
    for path in SRC.rglob("*.py"):
        if path.is_relative_to(SRC / "facts"):
            continue
        assert not pattern.search(path.read_text()), f"{path} defines piece values"


# -- 5. reasons ------------------------------------------------------------------------------------


def test_every_fact_sentinel_literal_is_a_closed_code() -> None:
    literal = re.compile(r'Not(?:Applicable|Computed)\("([^"]*)"\)')
    for path in (SRC / "facts").rglob("*.py"):
        for code in literal.findall(path.read_text()):
            assert code in FACT_REASONS, f"{path.name}: {code!r}"


def _sentinels(value, out: list) -> None:
    if isinstance(value, NotApplicable | NotComputed):
        out.append(value.reason)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for f in dataclasses.fields(value):
            _sentinels(getattr(value, f.name), out)
    elif isinstance(value, tuple | list):
        for x in value:
            _sentinels(x, out)


def test_every_sentinel_of_a_tree_has_a_closed_code() -> None:
    engine = FactEngine()
    tree = engine.open(OpenRequest(root=RootSpec()))
    from calliope.facts import PLAYED, EnsureRequest, ExtendRequest

    engine.extend(tree, ExtendRequest((InputLine("g", ("e4", "e5", "Nf3", "Nc6", "Bb5")),), PLAYED))
    view = tree.view()
    nodes = view.input_line("g").nodes
    engine.ensure(tree, EnsureRequest(nodes, ("exchange",)))
    view = tree.view()
    found: list[str] = []
    for node in nodes:
        for family in view.families():
            _sentinels(view.fact(family, node), found)
        _sentinels(view.basis(node), found)
    assert found and set(found) <= FACT_REASONS


def test_every_reasoning_reason_literal_is_in_the_table() -> None:
    literal = re.compile(r'"NOT_COMPUTED\(([A-Za-z_0-9]+)\)"')
    for path in (SRC / "reasoning").rglob("*.py"):
        for code in literal.findall(path.read_text()):
            assert code in R.NOT_COMPUTED_CODES, f"{path.name}: NOT_COMPUTED({code})"
    assert set(REFUSALS) <= R.NOT_COMPUTED_CODES
    assert set(REASONS) <= {c.removeprefix("reason.") for c in IDS if c.startswith("reason.")}


def test_every_refusal_type_the_facts_api_raises_is_listed() -> None:
    from calliope.facts import FactEngineError

    def subclasses(kind):
        for sub in kind.__subclasses__():
            yield sub
            yield from subclasses(sub)

    raised = {k.__name__ for k in subclasses(FactEngineError)} | {"FactEngineError"}
    internal = {"InvalidRequestError", "IllegalMoveError", "StoredTreeError",
                "InvalidPositionError", "UnsupportedVariantError"}  # raised as malformed input, not refused  # fmt: skip
    assert raised - internal <= set(REFUSALS), sorted(raised - internal - set(REFUSALS))


# -- 6. builds -------------------------------------------------------------------------------------


def test_the_registry_digest_is_in_the_build_and_a_threshold_changes_it(monkeypatch) -> None:
    from calliope.reasoning import build_digest
    from calliope.reasoning.catalogue import material

    reasoner = Reasoner(FactEngine())
    before = reasoner.build()
    assert before.definitions == R.REGISTRY_DIGEST
    monkeypatch.setattr(material, "GAIN_CP_PER_POINT", 81)
    after = reasoner.build()
    assert after.definitions != before.definitions
    assert build_digest(after) != build_digest(before)


def test_the_fact_build_records_the_reason_codes() -> None:
    assert fact_storage.FACTS_BUILD_VERSION == "3"  # stored sentinels carry codes (DF-D §8)


@pytest.mark.parametrize("kind", [VerdictStatus, Quantifier, RelationKind])
def test_vocabulary_enums_are_strings(kind: type[Enum]) -> None:
    assert all(isinstance(m.value, str) for m in kind)
