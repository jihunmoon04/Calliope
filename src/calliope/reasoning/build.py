"""The reasoning build identity (R0-D §14.1 as amended by Q-D §6 and R4-D §2.1).

A `ReasoningBuild` names everything that can change a stored claim graph's bytes for the same
request: the fact build, the templates, the policies, the label rules and their parameters, the
phrasebook (name and file digest) and the grading build. It is taken from the reasoner that ran
(R4-D review B4), never assumed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from calliope.facts import BuildIdentity, build_identity, types_digest

REASONING_BUILD_VERSION = 1
ENCODING = "fact_encoding_v1"
POLICIES = ("quality_v1", "quality_v2", "label_v1", "label_v2", "selection_v1")
LABEL_RULES = ("forced_v1", "brilliant_p2", "great_p2", "miss_v1", "miss_p2")


@dataclass(frozen=True, slots=True)
class ReasoningBuild:
    reasoning_build_version: int
    facts: BuildIdentity
    encoding: str
    types: str  # digest of the reasoning type registry
    templates: tuple[tuple[str, str], ...]  # (name, version), in registry order
    policies: tuple[str, ...]
    label_rules: tuple[str, ...]
    label_parameters: tuple[tuple[str, tuple[int, ...]], ...]
    phrasebooks: tuple[tuple[str, str], ...]  # (name, sha256 of the file)
    grading: tuple  # GradingBuild.identity(): policies, curves, conversions, LOGISTIC digest


def _label_parameters() -> tuple[tuple[str, tuple[int, ...]], ...]:
    from calliope.reasoning.catalogue.exchange import NEAR_BEST, NOT_BAD, OFFER_MIN, WINNING
    from calliope.reasoning.labels import MISS_LOSS, MISS_OPPORTUNITY

    return (
        ("brilliant_p2", (OFFER_MIN, NEAR_BEST, NOT_BAD, WINNING)),
        ("miss_p2", (MISS_OPPORTUNITY, MISS_LOSS)),
    )


def _phrasebooks() -> tuple[tuple[str, str], ...]:
    from importlib import resources

    from calliope.reasoning.render import PHRASES_EN_V1

    data = resources.files("calliope.reasoning.render").joinpath("phrases/en.toml").read_bytes()
    return ((PHRASES_EN_V1, hashlib.sha256(data).hexdigest()),)


def reasoning_build(families, templates, grading_build) -> ReasoningBuild:
    """The build of a reasoner with these fact families, templates and grading build."""

    from calliope.reasoning.encoding import reasoning_registry

    return ReasoningBuild(
        REASONING_BUILD_VERSION,
        build_identity(tuple(families)),
        ENCODING,
        types_digest(reasoning_registry()),
        tuple((t.name, t.version) for t in templates),
        POLICIES,
        LABEL_RULES,
        _label_parameters(),
        _phrasebooks(),
        grading_build.identity(),
    )
