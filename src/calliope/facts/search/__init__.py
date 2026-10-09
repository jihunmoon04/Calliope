"""Engine searches for the fact engine (design F4-D): the boundary, records and the store.

`uci.StockfishEngine` is the only code that talks to an engine process.
"""

from calliope.facts.search.inputs import EngineInput, node_input, window_input
from calliope.facts.search.port import (
    Bound,
    EnginePort,
    RawLine,
    RawSearch,
    ScriptedEngine,
    SearchRequest,
    StoppedBy,
)
from calliope.facts.search.profile import (
    SUPPORTED_ENGINE,
    EngineIdentity,
    EngineOption,
    EngineProfile,
)
from calliope.facts.search.records import (
    Cp,
    EngineLineFact,
    EngineSearch,
    Mate,
    ReuseSource,
    SearchKind,
    SearchRuntime,
    Wdl,
    normalize,
    request_key,
)
from calliope.facts.search.store import EngineResultStore, Searcher
from calliope.facts.search.uci import StockfishEngine

__all__ = [
    "SUPPORTED_ENGINE",
    "Bound",
    "Cp",
    "EngineIdentity",
    "EngineInput",
    "EngineLineFact",
    "EngineOption",
    "EnginePort",
    "EngineProfile",
    "EngineResultStore",
    "EngineSearch",
    "Mate",
    "RawLine",
    "RawSearch",
    "ReuseSource",
    "ScriptedEngine",
    "SearchKind",
    "SearchRequest",
    "SearchRuntime",
    "Searcher",
    "StockfishEngine",
    "StoppedBy",
    "Wdl",
    "node_input",
    "normalize",
    "request_key",
    "window_input",
]
