"""The local analysis server (AS-D): the game pipeline, the ply cache, jobs and the HTTP API.

A redesign package: it never imports the legacy MVP, and nothing in facts, reasoning or results
imports it (`tests/test_package_boundaries.py`).
"""

from calliope.server.cache import PlyCache, StoreFailed
from calliope.server.commentary import (
    CommentaryStore,
    game_key,
    listing,
    stale,
    subject_digest,
    with_commentary,
)
from calliope.server.pipeline import (
    EngineSlot,
    InputError,
    JobFailed,
    ParsedGame,
    PlyProgress,
    analyse_game,
    analyse_ply,
    game_input,
    grading_for,
    normalized_ply,
    parse_game,
    plies_range,
    ply_request,
)

__all__ = [
    "CommentaryStore",
    "EngineSlot",
    "InputError",
    "JobFailed",
    "ParsedGame",
    "PlyCache",
    "PlyProgress",
    "StoreFailed",
    "analyse_game",
    "analyse_ply",
    "game_input",
    "game_key",
    "grading_for",
    "listing",
    "normalized_ply",
    "parse_game",
    "plies_range",
    "ply_request",
    "stale",
    "subject_digest",
    "with_commentary",
]
