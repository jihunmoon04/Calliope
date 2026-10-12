"""The local analysis server (AS-D): the game pipeline, the ply cache, jobs and the HTTP API.

A redesign package: it never imports the legacy MVP, and nothing in facts, reasoning or results
imports it (`tests/test_package_boundaries.py`).
"""

from calliope.server.cache import PlyCache, StoreFailed
from calliope.server.pipeline import (
    EngineSlot,
    InputError,
    JobFailed,
    ParsedGame,
    PlyProgress,
    analyse_game,
    game_input,
    grading_for,
    normalized_ply,
    parse_game,
    plies_range,
    ply_request,
)

__all__ = [
    "EngineSlot",
    "InputError",
    "JobFailed",
    "ParsedGame",
    "PlyCache",
    "PlyProgress",
    "StoreFailed",
    "analyse_game",
    "game_input",
    "grading_for",
    "normalized_ply",
    "parse_game",
    "plies_range",
    "ply_request",
]
