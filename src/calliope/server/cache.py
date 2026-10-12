"""The ply cache (AS-D §4): one bundle pair per normalized ply request, reused by replay.

A ply enters the game document only as it was loaded back from its files, whether it was just
analysed (`put`) or found (`get`), so `bundle.stored` is true in both and the bytes agree
(AS-D §3, re-review B1).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from calliope.facts import FactEngine, StoredTreeError
from calliope.reasoning import StoredGraphError
from calliope.reasoning.storage import load, save
from calliope.results import Bundle
from calliope.server.files import atomic_write, read_or_none

KEY_VERSION = "ply_key_v1"


class StoreFailed(Exception):
    """A just-stored bundle did not re-load to the same bytes (AS-D §3): a defect."""


@dataclass(frozen=True, slots=True)
class Loaded:
    analysis: object  # Analysis, as replayed from the files
    rendered: object  # RenderedExplanation, as stored
    bundle: Bundle


def canonical(value) -> bytes:
    """Compact UTF-8 JSON with sorted keys: the preimage of the cache key and the job id."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class PlyCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    @staticmethod
    def key(request, build_digest: str, identity, profile) -> str:
        """The sha256 of AS-D §4's preimage; `request` is `normalized_ply(...)`."""

        preimage = {
            "v": KEY_VERSION,
            "build": build_digest,
            "engine": list(identity.fingerprint()),
            "profile": list(profile.fingerprint()),
            "root": {"fen": request.root.fen, "moves": list(request.root.moves)},
            "moves": list(request.moves),
            "target": request.target,
            "budget": asdict(request.budget),
            "language": request.language,
            "grading": asdict(request.grading),
        }
        return hashlib.sha256(canonical(preimage)).hexdigest()

    def paths(self, key: str) -> tuple[Path, Path]:
        folder = self.root / key[:2]
        return folder / f"{key}.tree", folder / f"{key}.graph"

    def get(self, key: str, expected, build) -> Loaded | None:
        """The stored ply, or None on a miss (AS-D §4, review B2): a missing or unreadable file,
        a tree or graph that fails to load, or another request or build."""

        tree_path, graph_path = self.paths(key)
        graph = read_or_none(graph_path)  # written last: present means the pair was complete
        tree = read_or_none(tree_path) if graph is not None else None
        if tree is None or graph is None:
            return None
        try:
            analysis, rendered = load(FactEngine(), tree, graph)
        except (StoredTreeError, StoredGraphError):
            return None
        if analysis.round_zero.request != expected or analysis.build != build:
            return None
        return Loaded(analysis, rendered, _bundle(tree, graph))

    def put(self, key: str, analysis, rendered, expected, build) -> Loaded:
        """Save, write (tree first, graph last), read back and re-load: only a pair that re-loads
        to the same bytes is used (AS-D §3). Otherwise the files are removed."""

        tree, graph = save(analysis, rendered)
        tree_path, graph_path = self.paths(key)
        atomic_write(tree_path, tree)
        atomic_write(graph_path, graph)
        try:
            back_tree, back_graph = tree_path.read_bytes(), graph_path.read_bytes()
            loaded, again = load(FactEngine(), back_tree, back_graph)
            if save(loaded, again) != (tree, graph):
                raise StoreFailed("the re-loaded analysis saves to other bytes")
            if loaded.round_zero.request != expected or loaded.build != build:
                raise StoreFailed("the stored request or build is not the expected one")
        except (OSError, StoredTreeError, StoredGraphError, StoreFailed) as error:
            graph_path.unlink(missing_ok=True)
            tree_path.unlink(missing_ok=True)
            raise StoreFailed(f"{type(error).__name__}: {error}") from error
        return Loaded(loaded, again, _bundle(tree, graph))


def _bundle(tree: bytes, graph: bytes) -> Bundle:
    return Bundle(hashlib.sha256(tree).hexdigest(), hashlib.sha256(graph).hexdigest(), stored=True)
