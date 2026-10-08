"""P12 internal RenderedCommentary value: structure only, never proof of anything."""

import ast
import dataclasses
from pathlib import Path

import pytest

import calliope
import calliope.domain.explanation as explanation_package
from calliope.domain.explanation import RenderedCommentary
from calliope.domain.explanation.render import NO_VERIFIED_EXPLANATION
from calliope.errors import CalliopeError, ExplanationRenderError

ONE = "Move c3e4 allows an engine-verified line with material loss."
TWO = "Move c3e4 leaves white knight from c3 hanging."


def test_error_is_a_calliope_error():
    assert issubclass(ExplanationRenderError, CalliopeError)


def test_frozen_meta_text():
    assert NO_VERIFIED_EXPLANATION == "No verified explanation is available."


def test_valid_non_empty_commentary():
    value = RenderedCommentary(
        text=f"{ONE} {TWO}", sentences=(ONE, TWO), used_claim_ids=("cl_002", "cl_001")
    )
    assert value.text == " ".join(value.sentences)
    assert tuple(zip(value.used_claim_ids, value.sentences, strict=True)) == (
        ("cl_002", ONE),
        ("cl_001", TWO),
    )


def test_valid_empty_meta_shape():
    value = RenderedCommentary(text=NO_VERIFIED_EXPLANATION, sentences=(), used_claim_ids=())
    assert value.sentences == () and value.used_claim_ids == ()


def test_frozen_slots_and_field_order():
    value = RenderedCommentary(text=ONE, sentences=(ONE,), used_claim_ids=("cl_001",))
    assert [f.name for f in dataclasses.fields(RenderedCommentary)] == [
        "text",
        "sentences",
        "used_claim_ids",
    ]
    assert not hasattr(value, "__dict__")
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.text = TWO  # type: ignore[misc]


INVALID = {
    "empty-text": {"text": "", "sentences": (), "used_claim_ids": ()},
    "non-string-text": {"text": None, "sentences": (ONE,), "used_claim_ids": ("cl_001",)},
    "empty-sentence": {"text": " ", "sentences": ("", ""), "used_claim_ids": ("cl_001", "cl_002")},
    "non-string-sentence": {"text": ONE, "sentences": (1,), "used_claim_ids": ("cl_001",)},
    "sentences-list": {"text": ONE, "sentences": [ONE], "used_claim_ids": ("cl_001",)},
    "ids-list": {"text": ONE, "sentences": (ONE,), "used_claim_ids": ["cl_001"]},
    "noncanonical-id": {"text": ONE, "sentences": (ONE,), "used_claim_ids": ("cl_1",)},
    "evidence-id": {"text": ONE, "sentences": (ONE,), "used_claim_ids": ("ev_001",)},
    "duplicate-id": {
        "text": f"{ONE} {ONE}",
        "sentences": (ONE, ONE),
        "used_claim_ids": ("cl_001", "cl_001"),
    },
    "fewer-sentences": {"text": ONE, "sentences": (ONE,), "used_claim_ids": ("cl_001", "cl_002")},
    "more-sentences": {
        "text": f"{ONE} {TWO}",
        "sentences": (ONE, TWO),
        "used_claim_ids": ("cl_001",),
    },
    "text-join-mismatch": {
        "text": f"{ONE}  {TWO}",
        "sentences": (ONE, TWO),
        "used_claim_ids": ("cl_001", "cl_002"),
    },
    "text-reordered": {
        "text": f"{TWO} {ONE}",
        "sentences": (ONE, TWO),
        "used_claim_ids": ("cl_001", "cl_002"),
    },
    "text-causal-merge": {
        "text": f"{ONE[:-1]} because {TWO[0].lower()}{TWO[1:]}",
        "sentences": (ONE, TWO),
        "used_claim_ids": ("cl_001", "cl_002"),
    },
    "empty-with-sentences": {"text": ONE, "sentences": (ONE,), "used_claim_ids": ()},
    "empty-with-other-text": {"text": "The move is fine.", "sentences": (), "used_claim_ids": ()},
    "meta-text-as-sentence": {
        "text": NO_VERIFIED_EXPLANATION,
        "sentences": (NO_VERIFIED_EXPLANATION,),
        "used_claim_ids": (),
    },
}


@pytest.mark.parametrize("name", sorted(INVALID))
def test_invalid_shapes_fail_closed(name):
    with pytest.raises(ExplanationRenderError):
        RenderedCommentary(**INVALID[name])


def test_render_value_is_internal_only():
    assert "RenderedCommentary" in explanation_package.__all__
    assert not hasattr(calliope, "RenderedCommentary")
    assert not hasattr(calliope, "DeterministicExplanationRenderer")


RENDER_MODULE = Path(explanation_package.__file__).parent / "render.py"


def test_render_module_imports_only_domain_values():
    tree = ast.parse(RENDER_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            imported.add(node.module or "")
    assert {n for n in imported if n.startswith("calliope")} == {
        "calliope.errors",
        "calliope.domain.explanation.graph",
    }
    assert "contracts" not in RENDER_MODULE.read_text(encoding="utf-8")
