"""Internal immutable MVP-P12 rendered commentary value.

Structural container only.  Constructing one proves nothing about the claims it names; the
P12 renderer produces it only after P11 pair revalidation.  It is deliberately separate from
the public ``CommentaryView``, which belongs to the later application boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.domain.explanation.graph import _require_ids
from calliope.errors import ExplanationRenderError

NO_VERIFIED_EXPLANATION = "No verified explanation is available."
"""Frozen A0 §5 meta-level text for an empty validated selection; not a chess proposition."""


@dataclass(frozen=True, slots=True)
class RenderedCommentary:
    """Deterministic commentary: one sentence per used claim, in selection order.

    ``zip(used_claim_ids, sentences)`` is the claim-to-language provenance surface.  An empty
    selection carries the meta text with no sentences and no claim ids.
    """

    text: str
    sentences: tuple[str, ...]
    used_claim_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text:
            raise ExplanationRenderError("commentary text must be a non-empty string")
        if not isinstance(self.sentences, tuple):
            raise ExplanationRenderError("commentary sentences must be a tuple")
        if any(not isinstance(s, str) or not s for s in self.sentences):
            raise ExplanationRenderError("commentary sentences must be non-empty strings")
        _require_ids(self.used_claim_ids, "cl", "used_claim_ids", ExplanationRenderError)
        if not self.used_claim_ids:
            if self.sentences != () or self.text != NO_VERIFIED_EXPLANATION:
                raise ExplanationRenderError(
                    "commentary without claims must be exactly the frozen meta text"
                )
            return
        if len(self.sentences) != len(self.used_claim_ids):
            raise ExplanationRenderError("commentary needs exactly one sentence per claim")
        if self.text != " ".join(self.sentences):
            raise ExplanationRenderError("commentary text must be its sentences joined by a space")
