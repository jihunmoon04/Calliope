# Legacy removal — LR-D design

Status: **rev. 2 — independent review READY_WITH_CORRECTIONS applied (§11); owner decisions recorded (§9)**.
Date: 2026-10-12. Base: `main @ fa6e951`. Inputs:
[`redesign-status-and-roadmap.md`](redesign-status-and-roadmap.md) §5.2 item 5 ("once the new
blocks cover `analyze_move`, one PR deletes the legacy code, tests and `docs/legacy/`; tag
`legacy-mvp-g0` keeps the history"); [`../README.md`](../README.md) (the current-vs-legacy rules).

The MVP implementation has been frozen since 2026-10-08. The redesign now covers what the MVP
was for: one move analysed and explained, and a whole game, with a result document, a viewer and
a local server. This packet defines what is removed, how the history stays reachable, and which
rules change.

## 0. Decisions

| # | Decision |
| --- | --- |
| L1 | **The condition of roadmap item 5 holds** (§1): `analyze_move` and `analyze_game` are replaced, and no redesign code, test or tool depends on the legacy. |
| L2 | **Everything legacy goes in one PR** (§2): the legacy source modules, their tests, `benchmarks/`, `docs/legacy/`, and the legacy facade of `calliope/__init__.py`. |
| L3 | **A new tag `legacy-final`** marks the last `main` commit that still holds the legacy. It is pushed before the removal is merged. `legacy-mvp-g0` stays as it is. |
| L4 | **References keep their paths** (§3). A current document's `docs/legacy/...` path is read at tag `legacy-final`, where it still exists with that path. Only markdown links that would break are rewritten. Code comments that cite the legacy ("legacy P8 §12.0") stay. |
| L5 | **The rules are simplified** (§4). `CLAUDE.md`, `docs/README.md`, the top-level `README.md` and `tests/README.md` no longer describe a frozen legacy in the tree; they name the tags. |
| L6 | **The package root holds no names** (§5). `import calliope` loads nothing; each package is imported by its own name. |
| L7 | **What is lost is recorded, not ported** (§6). The MVP's positional observation sections have no redesign equivalent yet. A later design may restate them from the tag. |
| L8 | **Entry conditions of LR1** (rev. 2, review C1, C2). LR1 starts only when the owner has (a) approved that the schema 0.3 observation sections stop being available, unported, and (b) confirmed whether anything outside the repository uses the MVP API, and decided that no compatibility is kept. LR1 merges only after the tag check of §3 passes. |

## 1. Why the condition holds

| MVP operation (`calliope.engine.CalliopeEngine`) | Redesign |
| --- | --- |
| `analyze_move(AnalyzeMoveRequest)` → `MoveAnalysisResult` (schema 0.2) | `Reasoner.analyse(AnalysisRequest)` → `Analysis`; `explain(analysis)` → `RenderedExplanation`; `calliope_result_v1` (AR-D) |
| `analyze_game(AnalyzeGameRequest)` → `GameAnalysisResult` | `tools/explain_game`, `calliope.server` (AS-D) |
| `analyze_move_with_observations(ObservedMoveRequest)` → schema 0.3 observation sections | none (§6) |

Dependencies, checked on `main @ fa6e951`:
- `src/calliope/{facts,reasoning,results,server}` import no legacy module
  (`tests/test_package_boundaries.py` enforces it), and `tools/` neither
  (`test_tools_do_not_import_legacy`).
- No redesign test reads a legacy file: nothing under `tests/{facts,reasoning,results,server,
  tools,viewer}` names `docs/legacy`, `tests/golden`, `tests/unit` or `benchmarks`.
- The redesign code cites the legacy only in comments (for example `facts/flow.py`: "legacy P8
  §12.0"; `reasoning/observer.py`: "legacy `_slower_grade`").
- The repository has no CI configuration (`.github/` does not exist).
- The MVP had no Korean output, so nothing in that direction is lost.

## 2. What is removed

| Path | Content | Size |
| --- | --- | --- |
| `src/calliope/adapters/`, `application/`, `domain/`, `services/` | the MVP implementation | 71 files, about 15 500 lines |
| `src/calliope/composition.py`, `contracts.py`, `engine.py`, `errors.py` | the MVP facade and contracts | 575 lines |
| `tests/unit/`, `tests/integration/`, `tests/golden/` | the MVP's tests | 80 files, about 30 000 lines; 3 290 of the suite's 4 276 tests |
| `benchmarks/` | `observation_bridge_cost.py`, `scenario_summary_smoke.py`, a README (MVP only) | 3 files |
| `docs/legacy/` | the MVP documents and corpora | 35 files, about 11 800 lines of markdown |

Changed, not removed:
- `src/calliope/__init__.py` (§5);
- `tests/test_package_boundaries.py` (§5);
- `CLAUDE.md`, `docs/README.md`, `README.md`, `tests/README.md`, `docs/design/README.md` (§4);
- `docs/design/redesign-status-and-roadmap.md`: item 5 recorded as done.

Not touched: the tags `legacy-mvp-g0`, `abandoned/*` and `archive/*`; the frozen design records
of merged packets, apart from the one link of §3.

## 3. References to the legacy

- **Code spans keep their paths.** The current documents cite legacy evidence as code spans:
  documents such as `docs/legacy/positional-activity-design.md` (A0 §12, F2-D §0, F3-D §0,
  R0-D §2), MVP code such as `src/calliope/services/...` (A0 §12, F3-D §1, R0-D §2), and MVP
  tests and corpora such as `tests/unit/services/position/test_positional_foundation.py` and
  `tests/golden/scenario_explanation_cases.json` (F2-D §10; rev. 2, review C3). All of them
  exist at tag `legacy-final` with those paths. `docs/README.md` states once that a path under
  `docs/legacy/`, a removed `src/calliope/` module, `tests/unit/`, `tests/integration/`,
  `tests/golden/` or `benchmarks/` is read at that tag (§4). The packet records stay
  byte-identical, including the implementation records whose tables name the legacy suites
  (F1, F2, F3, F4b, F5, R1).
- **Markdown links that would break are rewritten** to plain text naming the tag:
  - `docs/design/README.md`: the link to `../legacy/README.md`;
  - `docs/README.md`: the link to `legacy/README.md`;
  - `README.md`: the links to `docs/legacy/README.md` and `docs/legacy/mvp-readme.md`.
- **Why a new tag.** `legacy-mvp-g0` predates the documentation split (#36): at that tag the
  documents live under `docs/` without `legacy/`, so `docs/legacy/...` paths do not resolve
  there. `legacy-final` is the last commit where both the code and `docs/legacy/` exist in their
  final form.
- **Tag procedure** (rev. 2, review C2). `main` may move while LR1 is open, so the tag is
  bound to the commit the removal actually follows, immediately before the merge:
  1. LR1's branch is rebased onto the current `main` (or `main` is merged into it), so its
     base `B` is `main`'s head.
  2. `git tag legacy-final B` and `git push origin legacy-final`.
  3. **Check** (each must hold, else LR1 is not merged):
     - `git ls-remote --tags origin legacy-final` names `B`;
     - `B` is `main`'s head at that moment and the merge base of LR1's branch and `main`;
     - at `B` the legacy is complete: `git cat-file -e B:<path>` for `src/calliope/engine.py`,
       `src/calliope/services`, `docs/legacy/README.md`, `tests/golden`, `tests/unit`,
       `tests/integration`, `benchmarks/README.md`, and every code-span path of §7.3;
  4. LR1 is merged with no further commit on `main` in between. If `main` moved, the tag is
     deleted (`git push origin :legacy-final`), and steps 1–3 run again.
  - The LR1 record names `B`, the tag object and the check's output.

## 4. Rules after the removal

- **`CLAUDE.md`.**
  - The "Current vs legacy" rule becomes: only `docs/design/` states current requirements and
    decisions; the MVP is history at tags `legacy-final` (code and `docs/legacy/`) and
    `legacy-mvp-g0`, cited as evidence by path and tag, never as authority.
  - The import rule becomes the redesign packages' own rules (the next item).
  - The packet rule is unchanged.
- **`tests/test_package_boundaries.py`** keeps every rule between the redesign packages and
  replaces the legacy rules:
  - `src/calliope/` holds only `__init__.py` and the packages `facts`, `reasoning`, `results`,
    `server` (a new legacy-like module cannot appear unnoticed);
  - `import calliope` loads no submodule;
  - kept: no redesign module imports the root package `calliope` (today part of
    `test_new_packages_do_not_import_legacy`, moved into its own test); facts never imports
    reasoning; nothing below results or server imports them; the public-name rules of
    reasoning, results and server; python-chess only where allowed;
  - removed: the four legacy tests (`test_new_packages_do_not_import_legacy`,
    `test_legacy_does_not_import_new_packages`, `test_legacy_facade_names_still_resolve`,
    `test_tools_do_not_import_legacy`), which have nothing left to check.
- **`docs/README.md`.** One area, `design/`. A section "History" names the tags and says how to
  read a cited legacy path: `git show legacy-final:<path>`, for paths under `docs/legacy/`, the
  removed `src/calliope/` modules, `tests/unit/`, `tests/integration/`, `tests/golden/` and
  `benchmarks/` (rev. 2, review C3).
- **The roadmap's verification commands** (`redesign-status-and-roadmap.md`, the line "legacy:
  `pytest tests/unit tests/golden`") lose the legacy line.
- **`README.md`.** The status table lists the redesign packages and tools and the viewer; the
  MVP row points to the tags.
- **`tests/README.md`.** The MVP layer plan is replaced by the current layout (one directory per
  block, plus `tools/` and `viewer/`).

## 5. The package root

- **Before.** `calliope/__init__.py` lazily re-exports 15 MVP names (`CalliopeEngine`,
  `AnalyzeMoveRequest`, …) and resolves them on first access.
- **After.** It holds a docstring naming the packages and no names. `import calliope` loads no
  submodule, as today. A caller that used `calliope.CalliopeEngine` gets an `AttributeError`.
- No redesign code imports the root package; the boundary tests refuse it today and keep
  refusing it (§4).

## 6. What is lost

- **Positional observation sections** (`analyze_move_with_observations`, schema 0.3): piece
  activity, scenario and exchange-line summaries, the played-transition observations. The
  redesign has its own observations (R2-D: the observer's lines and windows) but not these
  sections. They are not ported. If they are wanted, a new design packet restates them, using
  `docs/legacy/positional-activity-design.md`, `scenario-line-summary-design.md`,
  `exchange-line-summary-design.md` and the I1–I3 documents at tag `legacy-final` as evidence,
  and moves their verified cases into the new fact and reasoning contracts as new tests, rather
  than re-running the tag's tests (review note).
- **Schema 0.2 / 0.3 and the MVP's public API.** Callers move to `calliope_result_v1` and the
  redesign packages. No caller of the MVP API is known outside the repository (an open
  question for the owner, §9).
- **The MVP's corpora** (`docs/legacy/corpus/`, `tests/golden/*.json`). The redesign's own
  acceptance corpus (R4-D §4) replaces them for the redesign. They stay readable at the tag.

## 7. Test obligations (packet LR1)

1. **The whole suite passes** after the removal; its count falls by the MVP's tests (3 290 at
   `fa6e951`), and nothing else is skipped or lost: the redesign test count is unchanged.
2. **The new boundary tests** (§4) pass, and each fails when a planted module (for example
   `src/calliope/engine.py`) or a planted import is added.
3. **No dangling reference.**
   - `git grep` finds no import of the removed modules anywhere.
   - No markdown link (`](...)`) points into `docs/legacy/`, `tests/unit`, `tests/integration`,
     `tests/golden` or `benchmarks/`.
   - Every code-span path in `docs/design/` under `docs/legacy/`, a removed `src/calliope/`
     module, `tests/unit/`, `tests/integration/`, `tests/golden/` or `benchmarks/` exists at
     tag `legacy-final` (`git cat-file -e legacy-final:<path>`, line ranges dropped; recorded in
     the LR1 record, not a test, since the tag is not in every clone).
3a. **The tag check of §3** passes, and its output is in the LR1 record (review C2).
4. **The tools still run**: `tools/explain_game` on a short PGN with the synthetic engine (the
   existing tool tests), `tools/serve --help`.
5. **The suite's duration** before and after is recorded.

## 8. What stays the same
- Every redesign package, tool, test and the viewer.
- The packet process.
- The roadmap's other items; item 5 is recorded as done.

## 9. Owner decisions (L8: LR1's entry conditions)
Answered by the owner on 2026-10-12, after seeing the MVP's observation output next to the
redesign's explanation for four plies of the owner's 829/808 game (the MVP sections state
moves, captures, file states and attack footprints in internal notation, such as
`[FILE_STATE]: white_pawns=0, black_pawns=2`, and the MVP commentary was "No verified
explanation is available." on all four plies):

- **The observation sections** (§6): **approved** to stop, unported.
- **External callers** of the MVP API (`calliope.CalliopeEngine`, schema 0.2 / 0.3): **none**.
  No compatibility is kept.
- **The tag name**: **`legacy-final`** (L3).

L8's entry conditions therefore hold.

## 10. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| LR-D (this) | the removal's scope, references, rules | independent review READY |
| LR1 | after L8's owner decisions: one PR with the removals of §2, the changes of §3–§5, the roadmap, an LR1 record with §7's checks; the tag `legacy-final` bound and checked right before the merge (§3) | READY, and the tag check |

## 11. Review dispositions (rev. 1 `21fa12f`, independent review: READY_WITH_CORRECTIONS)

| Finding | Disposition |
| --- | --- |
| C1 the basic operations are replaced, but not every function: schema 0.3's observations are not | Valid. Applied (L8, §9): the owner's approval that the observation sections stop, and the decision on external callers and compatibility, are LR1's entry conditions, recorded in §9. |
| C2 `main` may move after the tag is made, so the tag may not be the commit before the removal | Valid. Applied (§3 tag procedure, §7.3a): the tag is made right before the merge from LR1's actual base, checked on the remote and against `main`, the legacy's presence at it is checked, and a moved `main` means re-tagging; the record keeps the SHA and the output. |
| C3 the history rule covered `docs/legacy/` and source, not tests, corpora and benchmarks | Valid: F2-D §10 cites `tests/unit/...` and `tests/golden/scenario_explanation_cases.json`. Applied (§3, §4, §7.3): `tests/unit/`, `tests/integration/`, `tests/golden/` and `benchmarks/` are read at the tag too; the roadmap's legacy test command goes. |
| (note) the removed tests' protection is gone | Recorded: if positional observations return, their cases move into the new fact and reasoning contracts (§6), rather than the tag's tests being re-run. |
