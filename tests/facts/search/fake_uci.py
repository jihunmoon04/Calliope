"""A scripted UCI engine for adapter tests (F4-D §9.1.1). Not part of the package.

Usage: python fake_uci.py SCRIPT.json LOG.txt
SCRIPT keys: name, options (list of option lines), searches (list of per-search line lists),
hang (bool: never send bestmove until `stop`), die_on_go (bool), start_error (bool).
Every received command is appended to LOG.
"""

import json
import sys
from pathlib import Path

script = json.loads(Path(sys.argv[1]).read_text())
searches = list(script.get("searches", []))


def out(line):
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


with open(sys.argv[2], "a", buffering=1) as log:
    for raw in sys.stdin:
        command = raw.strip()
        log.write(command + "\n")
        if command == "uci":
            out(f"id name {script.get('name', 'Stockfish 19')}")
            out("id author fake")
            for line in script.get(
                "options",
                [
                    "option name Threads type spin default 1 min 1 max 1024",
                    "option name Hash type spin default 16 min 1 max 33554432",
                    "option name Clear Hash type button",
                    "option name MultiPV type spin default 1 min 1 max 256",
                    "option name UCI_ShowWDL type check default false",
                    "option name EvalFile type string default nn-test.nnue",
                ],
            ):
                out(line)
            out("uciok")
        elif command == "isready":
            if script.get("start_error"):
                out("info string ERROR: network not loaded")
            out("readyok")
        elif command.startswith("go"):
            if script.get("die_on_go"):
                sys.exit(1)
            lines = searches.pop(0) if searches else []
            for line in lines:
                out(line)
            if not script.get("hang"):
                out("bestmove " + (lines[-1].split(" pv ")[1].split()[0] if lines else "0000"))
        elif command == "stop":
            out("bestmove 0000")
        elif command == "quit":
            break
