# Tests

One directory per block, plus the tools and the viewer:

| Directory | Tests |
| --- | --- |
| `facts/` | the fact engine: families, auditor, fuzz, engine adapter (Stockfish-gated parts) |
| `reasoning/` | the reasoner: grading, labels, catalogue, rendering, storage, the acceptance corpus |
| `results/` | `calliope_result_v1`: the builder, the schema, the dependency-free validator |
| `server/` | the analysis server: pipeline, cache, jobs, HTTP |
| `tools/` | the operator tools |
| `viewer/` | the viewer's pure part, under node |
| `test_package_boundaries.py` | the import rules between the packages |

Tests that need Stockfish 19 read `CALLIOPE_STOCKFISH_PATH` and are skipped without it.
The MVP's tests are history at tag `legacy-final` (`docs/README.md`).
