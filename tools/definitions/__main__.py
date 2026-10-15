"""`python -m tools.definitions [OUT]`: the definitions registry as `definitions_v1` JSON (DF-D §2).

Every entry of `calliope.reasoning.definitions.DEFINITIONS` (the fact engine's included), sorted by
id, with the registry digest that enters the reasoning build. Without OUT it writes to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from calliope.facts import definitions_json
from calliope.reasoning.definitions import DEFINITIONS, REGISTRY_DIGEST


def document() -> dict:
    return {"format": "definitions_v1", "digest": REGISTRY_DIGEST,
            "definitions": definitions_json(DEFINITIONS)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.definitions")
    parser.add_argument("out", nargs="?", type=Path, help="the JSON file to write (default stdout)")
    args = parser.parse_args(argv)
    text = json.dumps(document(), indent=1, ensure_ascii=False) + "\n"
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
