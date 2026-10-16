"""The agent package (AG-D): an MCP server for commentary agents.

The server gives an agent Calliope's judgements, claims and facts, judges and explores moves on
request under a budget metered at the engine port, and serves the Korean prompts, the glossary and
the registries. It imports only the public names of `calliope.facts`, `calliope.reasoning`,
`calliope.results` and `calliope.server` (and python-chess); nothing imports it
(`tests/test_package_boundaries.py`). The MCP SDK is the optional dependency group `agent`:
`calliope.agent.server` needs it, the session does not.
"""

from calliope.agent.budget import (
    Budget,
    BudgetError,
    Limits,
    Meter,
    MeteredPort,
    SearchBudgetExhausted,
    analysis_bound,
)
from calliope.agent.definitions import AGENT_DEFINITIONS, AGENT_DIGEST
from calliope.agent.games import GameError, from_record, pgn_tags
from calliope.agent.handles import HandleError, HandleExpired, Handles
from calliope.agent.session import AgentError, Session

__all__ = [
    "AGENT_DEFINITIONS",
    "AGENT_DIGEST",
    "AgentError",
    "Budget",
    "BudgetError",
    "GameError",
    "HandleError",
    "HandleExpired",
    "Handles",
    "Limits",
    "Meter",
    "MeteredPort",
    "SearchBudgetExhausted",
    "Session",
    "analysis_bound",
    "from_record",
    "pgn_tags",
]
