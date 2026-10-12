# Legacy removal — packet LR1 implementation

Status: **rev. 1 — awaiting independent review**.
Date: 2026-10-12. Design: [`legacy-removal-design.md`](legacy-removal-design.md) rev. 2 (LR-D,
review READY_WITH_CORRECTIONS applied, owner decisions in §9, merged #85). Base:
`main @ 7f842de`.

## 1. Entry conditions (LR-D L8)
- The owner approved dropping the MVP's observation sections, unported, and confirmed that no
  caller outside the repository uses the MVP API, so no compatibility is kept (LR-D §9).
- The tag check of LR-D §3 runs right before the merge; its result is §5.

## 2. Scope delivered

| Change | Content |
| --- | --- |
| removed | `src/calliope/{adapters,application,domain,services}/`, `src/calliope/{composition,contracts,engine,errors}.py`, `tests/{unit,integration,golden}/`, `benchmarks/`, `docs/legacy/`: 193 files, 66 192 lines |
| `src/calliope/__init__.py` | a docstring naming the packages and the tags; no names (LR-D §5) |
| `tests/test_package_boundaries.py` | new `test_src_holds_only_the_redesign_packages`, `test_no_package_imports_the_root_package` (packages and tools), `test_importing_the_package_loads_no_submodule`; the four legacy tests removed; every rule between the redesign packages kept (LR-D §4) |
| `CLAUDE.md` | "Current vs history": the tags, how to read a cited path; `src/calliope/` holds only the redesign packages |
| `docs/README.md` | one area, `design/`; a "History" section with the tags and the reading rule for cited paths |
| `README.md` | the blocks, how to use them, the history line |
| `tests/README.md` | the current layout |
| `docs/design/README.md` | the link into `docs/legacy/` replaced by text naming the tag; LR-D and LR1 rows |
| `docs/design/redesign-status-and-roadmap.md` | item 5 done; the legacy test command and the legacy rules removed from §7 |

The packet records are unchanged, including the code-span paths they cite (LR-D §3).

## 3. Implementation notes
1. **The leftover directories** held only `__pycache__` after `git rm` (checked: no file other
   than `*.pyc`), and were removed from the working tree.
2. **The root-package rule** was part of `test_new_packages_do_not_import_legacy`. It is now
   its own test and also covers `tools/`, which `test_tools_do_not_import_legacy` checked before.
3. **No other file named the removed paths**: `pyproject.toml` and `.gitignore` do not, and no
   CI configuration exists.

## 4. Checks (LR-D §7)

| Obligation | Result |
| --- | --- |
| 1 the suite | 963 passed, 21 skipped (984 collected); before: 4142 passed, 132 skipped (4 276) |
| 1 redesign tests unchanged | 986 collected before the removal outside the removed directories (`tests/{facts,reasoning,results,server,tools,viewer}` and the boundary file); 984 after (the boundary file: 11 → 9 tests: four legacy tests removed, two added) |
| 2 boundary tests and planted violations | 9 passed. A planted `src/calliope/engine.py` fails 1 test; `import calliope` planted in `calliope/server/files.py` fails 2; `import calliope` planted in `tools/serve/__init__.py` fails 1; all pass again after restoring |
| 3 imports of removed modules | `git grep` finds none outside `docs/design/`; there, two mentions in prose (AR-D G2, LR-D §1) |
| 3 markdown links | none into `docs/legacy/`, `tests/unit`, `tests/integration`, `tests/golden` or `benchmarks/` |
| 3 cited paths at the tag | 34 code-span paths in `docs/design/` under the removed roots; all 34 exist at the base commit (§5) |
| 3a the tag check | §5 |
| 4 the tools | `tools/explain_game` (its tests, in the suite), `python -m tools.serve --help`, `python -m tools.explain_game --help`; `import calliope` exposes no name and loads no submodule |
| 5 duration | before: 4142 passed, 132 skipped in 16 min 24 s (AS1 rev. 3, `main` before AS2); after: 13 min 54 s. The MVP's 3 290 tests took about 2.5 min; most of the time is the redesign's own suites (the facts fuzz and the corpus) |

## 5. The tag `legacy-final` (LR-D §3)

To be run right before the merge, with LR1's branch on the current `main` (its base `B`):

1. `git tag legacy-final B`; `git push origin legacy-final`;
2. `git ls-remote --tags origin legacy-final` names `B`; `B` is `main`'s head and the merge base;
3. `git cat-file -e B:<path>` for `src/calliope/engine.py`, `src/calliope/services`,
   `docs/legacy/README.md`, `tests/golden`, `tests/unit`, `tests/integration`,
   `benchmarks/README.md`, and the 34 cited paths;
4. merge with no commit on `main` in between; if `main` moved, delete the tag and repeat.

The SHA, the tag object and the output are recorded here when it has run.
