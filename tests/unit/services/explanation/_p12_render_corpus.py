"""P12 golden oracle over the reviewed P10 unit scenario corpus (not collected).

The packages are python-chess rules + scripted P7 engine, not real Stockfish.  The expected
sentences are an independent copy of the frozen A0 §10 wording, written out literally.
"""

from dataclasses import replace

import _p8_claim_scenarios as p8
import _p9_preservation_claim_scenarios as pres
import _p9_strong_claim_scenarios as strong

from calliope.domain.explanation import (
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    EvidenceBundle,
)
from calliope.services.explanation import (
    DeterministicExplanationRenderer,
    ExplanationSelectionValidator,
    ExplanationSelector,
    GraphBuilder,
)

_P = ClaimPredicate
_C = ClaimConfidence
_S = ClaimScope
EV = _C.ENGINE_VERIFIED
NO_VERIFIED_EXPLANATION = "No verified explanation is available."


def _defender_only():
    return p8.only_kind(p8.defender(), p8.Kind.REMOVED_DEFENDER)


def defender_without_unselected_claim():
    """p8.defender minus its REMOVED_DEFENDER cause: the claim P11 does not select."""

    result = p8.defender()
    causes = tuple(c for c in result.causes if c.kind is not p8.Kind.REMOVED_DEFENDER)
    return replace(result, causes=causes)


CORPUS = {
    "p8-knight": (p8.knight, p8),
    "p8-defender": (p8.defender, p8),
    "p8-defender-only": (_defender_only, p8),
    "p8-fork": (p8.fork, p8),
    "p8-exact-mate": (p8.exact_mate, p8),
    "p8-engine-mate": (p8.engine_mate, p8),
    **{f"strong-{make.__name__}": (make, strong) for make in strong.SCENARIOS},
    **{f"pres-{make.__name__}": (make, pres) for make in pres.SCENARIOS},
}

_PRES = "Compared with the tested representative alternatives, move h2h3 avoids the"
GOLDEN = {
    "p8-knight": (
        "Move c3e4 allows an engine-verified line with material loss.",
        "Move c3e4 leaves white knight from c3 hanging.",
    ),
    "p8-defender": (
        "Move c3c4 allows an engine-verified line with material loss.",
        "Move c3c4 leaves white knight from d4 hanging.",
    ),
    "p8-defender-only": ("Move c3c4 removes a defender of white knight from d4.",),
    # The retained fork pieces are the black actor plus white targets: no roles are printed.
    "p8-fork": (
        "Move d3e4 allows an engine-verified line with material loss.",
        "Move d3e4 allows a fork.",
    ),
    "p8-exact-mate": ("Move d1d7 allows checkmate.",),
    "p8-engine-mate": ("Move d1d7 allows an engine-verified mating line.",),
    "strong-forces": ("Move b1a1 forces response a8b8.",),
    "strong-exact_mate": ("Move f1f8 delivers checkmate.",),
    "strong-direct_mate": (
        "Move f1a1 has an engine-verified line leading to mate.",
        "Move f1a1 forces response h8g8.",
    ),
    "strong-ignored_mate": (
        "Move d2e3 creates a mate threat that tested response g8f8 does not meet.",
    ),
    "strong-direct_material": ("Move d1d5 has an engine-verified line that wins material.",),
    # a7a6 is the concrete ignoring reply that was tested and failed; it is not a defense.
    "strong-ignored_material": (
        "Move a1a5 creates a material threat that tested response a7a6 does not meet.",
    ),
    "pres-mate_all": (
        f"{_PRES} mate failure seen after d1a1 and d1b1.",
        f"{_PRES} material loss seen after d1a1 and d1b1.",
    ),
    "pres-mate_subset": (
        f"{_PRES} mate failure seen after d1a1.",
        f"{_PRES} material loss seen after d1a1.",
    ),
    "pres-engine_mate": (f"{_PRES} mate failure seen after f2f3.",),
    "pres-replayed_engine_mate": (
        f"{_PRES} mate failure seen after d1d7.",
        f"{_PRES} material loss seen after d1d7.",
    ),
    "pres-material_all": (f"{_PRES} material loss seen after d1d2 and d1d4.",),
    "pres-material_subset": (f"{_PRES} material loss seen after d1d2.",),
}

FORM_GOLDEN = {
    (_P.LEAVES_PIECE_HANGING, EV, _S.LOCAL): ("p8-knight", 1),
    (_P.REMOVES_DEFENDER, EV, _S.LOCAL): ("p8-defender-only", 0),
    (_P.ALLOWS_FORK, EV, _S.LOCAL): ("p8-fork", 1),
    (_P.ALLOWS_CHECKMATE, _C.EXACT, _S.LOCAL): ("p8-exact-mate", 0),
    (_P.ALLOWS_CHECKMATE, EV, _S.LOCAL): ("p8-engine-mate", 0),
    (_P.ALLOWS_MATERIAL_LOSS, EV, _S.LOCAL): ("p8-knight", 0),
    (_P.FORCES_RESPONSE, _C.EXACT, _S.LOCAL): ("strong-forces", 0),
    (_P.DELIVERS_CHECKMATE, _C.EXACT, _S.LOCAL): ("strong-exact_mate", 0),
    (_P.LEADS_TO_MATE, EV, _S.LOCAL): ("strong-direct_mate", 0),
    (_P.WINS_MATERIAL, EV, _S.LOCAL): ("strong-direct_material", 0),
    (_P.THREATENS_MATE_IF_IGNORED, EV, _S.TESTED_RESPONSE): ("strong-ignored_mate", 0),
    (_P.THREATENS_MATERIAL_IF_IGNORED, EV, _S.TESTED_RESPONSE): ("strong-ignored_material", 0),
    (_P.AVOIDS_REPRESENTATIVE_MATE_FAILURE, EV, _S.REPRESENTATIVE_ALTERNATIVES): (
        "pres-mate_all",
        0,
    ),
    (_P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS, EV, _S.REPRESENTATIVE_ALTERNATIVES): (
        "pres-material_all",
        0,
    ),
}
"""Each of the 14 current P10-valid forms -> (corpus package, sentence index) that shows it."""


def package(name):
    make, module = CORPUS[name]
    bundle = module.evidence(make())
    return bundle, module.claims(bundle)


def built(name):
    return GraphBuilder().build(*package(name))


def pair(name):
    graph = built(name)
    selection = ExplanationSelector().select(graph)
    assert ExplanationSelectionValidator().validate(graph, selection) is selection
    return graph, selection


def empty_pair(base_position_id="pos_base"):
    graph = GraphBuilder().build(EvidenceBundle(base_position_id, (), ()), ())
    return graph, ExplanationSelector().select(graph)


def render(name):
    return DeterministicExplanationRenderer().render(*pair(name))


def signature(rendered):
    return (rendered.text, rendered.sentences, rendered.used_claim_ids)
