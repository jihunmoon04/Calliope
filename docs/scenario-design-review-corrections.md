# A1 independent design review corrections — PR 29

Status: A1_READY.
Reviewed head: 094f4df0a48105ecdf522b4bd4d7e72d1834e59d.
Independent verdict supplied by reviewer: READY_WITH_CORRECTIONS.
F1-F5 were medium contract gaps; F6-F7 were low notes. All seven are addressed
in this packet. The subsequent independent re-review of c99d6a3 returned READY,
supplied by the user on 2026-10-08; this record reports that verdict, not self-review.

The reviewer verified production src equality with main dffd550, 28 corpus checks,
changed-file lint/diff and special-move facts. They did not repeat the 265-test
group. This correction packet distinguishes its own runs below.

## 1. Finding-to-contract traceability

| Finding | Correction | Structured / executable evidence |
| --- | --- | --- |
| F1: EP victim-square focus lacked a required event sentence | EXCHANGE section 3 defines FOCUS_VICTIM_SQUARE in addition to LINE_CONTEXT; capture remains non-focus, creates no participant/loss, and requires CAPTURE_EP in digest | E05 fixes both reasons, empty participants/losses, NO_FOCUS_CAPTURE, required digest landing d6 / victim d5 |
| F2: pin wording inferred excluded king motion and causality | Corpus E12 now describes pin presence after ply 1 and absence after ply 2 only; king MOVE excluded; common true/false pin templates are observational | E12 frame 3 absence added; complete [false,true,false,false,false] physical-pin track and included appearance/disappearance keys; endpoint pin is an absent candidate |
| F3: conflicting SourceRef ownership/shape and incomplete mixed provenance | Shared section 4 alone owns tagged references, FactKind/value pairs, sentinels and mandatory mixed-source bundles; EXCHANGE only references them | Exact observation/history bundles for occupant, attackers, rays, supporters, pins, captures and transitions; no optional-selector SourceRef definition in policy |
| F4: open candidate/accounting definitions | EXCHANGE section 5 closes domains, predicates, buckets, reasons and accounting location in one table; common section 5 defines all initial identities, comparison pairs, actual observed pin keys and source-supported ray directions | Separate complete key partitions for steps/endpoints/events/snapshots/aggregates; explicit PIECE_STATE/PARTITION/SUPPORTERS rows; E14 event exclusion and E13 endpoint exclusion fixed |
| F4: temporary count and participant timing ambiguous | Temporary count means nonconstant selected track with equal endpoint values, one per key; P is global physical membership and PinP tests that set even when pin absent | E12 exact pin track, selected step/history keys and equal-valued endpoint absence; no fabricated endpoint exclusion |
| F5: future acceptance depended on prose | v2 JSON fixes exact initial-square participants, status, focus_losses and core included/excluded/absent keys BEFORE A2 | All 15 cases have structured oracles; evidence verifier independently checks P5/physical histories and named candidate observations, not a future summary result |
| F6: only castling rook selected | Common catalog explicitly labels actual king castling UCI as step context and names physical rook endpoints; excluded king MOVE is not fabricated as a selected event | New E15 freezes participant rook h1, victim f7, included CASTLING_ROOK, excluded king MOVE and e1g1 context with h1-to-f1 endpoints |
| F7: semantic prohibition test mechanism open | Common section 6.1 gives closed TemplateIds, fixed reviewed forms and typed slot/context restrictions; unknown templates/text slots refused; word blacklist supplementary | E05/E12/E15 template obligations fixed in JSON; future A2 must enumerate every catalog branch, resolve sources and check coverage separately |

Shared contract: [scenario-line-summary-design.md](scenario-line-summary-design.md).
Policy: [exchange-line-summary-design.md](exchange-line-summary-design.md).
Corpus semantics/schema: [scenario-explanation-corpus.md](scenario-explanation-corpus.md).
Normative data: tests/golden/scenario_explanation_cases.json.

## 2. Validation of this correction packet

Direct execution against this worktree's explicit PYTHONPATH, with UTF-8 mode:

- 45 corpus checks: 15 factual cases, 15 mirrored capture/material controls,
  15 structured expectation evidence checks, all passed.
- 282 combined focused tests passed / 0 failed: the 45 corpus checks plus the
  prior 237 positional/activity/identity/python-chess/composition/facade tests.
- The imported calliope package path was printed and confirmed inside this worktree.
- Changed Python Ruff check and format check pass; git diff --check passes.
- Production src remains identical to main dffd550; no public contract/composition
  or runtime engine implementation changes.

Participant/status/loss assertions are exact. Core included/excluded keys are
manually specified membership obligations, not complete accounting sets generated
by a selector. Named keys are checked for actual event/property evidence; equal
absent keys are checked separately. No ScenarioSummary, selector, renderer or new
SourceRef exists yet, so their implementation/acceptance is not claimed.

No full pytest, Stockfish, fuzz, performance measurements or CI were run for this
packet. Template obligations are frozen for A2; they are not passing renderer tests.

## 3. Re-review gate

Re-review common sections 4-6, the EXCHANGE table and v2 JSON together. Verify
that every required corpus meaning can be emitted from selected typed values and
mandatory reference bundles, especially E05, E12 and E15. Check exact candidate
partitions, equal endpoint absences, template scope and loss/material separation.
Report READY, READY_WITH_CORRECTIONS or NOT_READY without treating this authored
correction record as the independent verdict. A2 begins only after corrections
are independently accepted.

## 4. Independent re-review closure

PR #29 head c99d6a3 was independently re-reviewed READY. The reviewer checked
all F1-F7 corrections, 45 corpus tests, worktree source import, source equality
with main dffd550, golden Ruff check/format and diff check. They did not repeat
the authored 282-test group. A2 is permitted; no implementation review is implied.

Nonblocking notes: N1 asks A2 acceptance to transform participants, losses and
fact keys on color mirrors; N2 defers required_templates checks to the actual A2
renderer. Both are covered by test_scenario_summary_acceptance.py; execution
evidence is in [scenario-summary-a2-implementation.md](scenario-summary-a2-implementation.md).
