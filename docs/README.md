# Calliope documentation

Calliope is built as composable blocks with one role each. The design documents are in
[`design/`](design/README.md): each block is designed in a packet (design document →
independent review → implementation packets, each reviewed), and only these documents state
current requirements and decisions.

## Rules

1. **Only `design/` is current.** A statement elsewhere, including the history below, is never a
   requirement, decision or contract, even when it is correct. If an old idea is still wanted, a
   `design/` document must restate it.
2. **New documents go to `design/`** and are listed in [`design/README.md`](design/README.md)
   with their status.
3. **Packet records are not rewritten.** A merged design or implementation record keeps its
   text; a later packet amends it in a section of its own.

## Code

| Code | Described by |
| --- | --- |
| `src/calliope/facts/` | the fact engine packets (F0–F6); CC1, DF1, PF1, PF2 |
| `src/calliope/reasoning/` | the reasoning packets (R0–R4, Q, LV, MV, EA, EV, EF, DF, MS-a) |
| `src/calliope/results/` | AR-D, AR1, DF1 |
| `src/calliope/server/`, `tools/serve/` | AS-D, AS1, AG2, AG3a, CC-D, CC1, PF-D, PF1, PF2 |
| `src/calliope/agent/`, `tools/mcp/` | AG-D and its packets (AG1–AG8, MS, CV4, BL, PW, LM) |
| `viewer/` | the static viewer, AS2, AG3a, AG3b |
| `tools/` | the operator tools of the packets that name them |

## History

The MVP implementation (P0–P12, G0, schema 0.2 / 0.3), its tests, `benchmarks/` and its
documents (`docs/legacy/`) were removed by LR1 (LR-D,
[`design/legacy-removal-design.md`](design/legacy-removal-design.md)). They are kept at tags:

| Tag | What it holds |
| --- | --- |
| `legacy-final` | the last commit with the MVP: code, tests, `benchmarks/`, `docs/legacy/` |
| `legacy-mvp-g0` | the MVP at G0, before its documents moved to `docs/legacy/` |
| `abandoned/*`, `archive/*` | abandoned design directions and archived states |

A current document may cite this history as *evidence*, never as authority. A cited path under
`docs/legacy/`, a removed `src/calliope/` module (`adapters`, `application`, `domain`,
`services`, `composition.py`, `contracts.py`, `engine.py`, `errors.py`), `tests/unit/`,
`tests/integration/`, `tests/golden/` or `benchmarks/` is read at `legacy-final`:

```sh
git show legacy-final:docs/legacy/positional-activity-design.md
git show legacy-final:tests/golden/scenario_explanation_cases.json
```
