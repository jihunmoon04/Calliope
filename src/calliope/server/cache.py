"""The ply cache (AS-D §4): one bundle pair per normalized ply request, reused by replay.

A just-analysed ply is written, its files read back and compared byte for byte with what was
saved, and the analysis the pipeline made is used (`checked: "written"`, CC-D C1): that loading
those bytes gives the same analysis is the storage code's property, proved by the tests; with
`verify_writes` the pair is loaded back and saved again, as before CC-D (`checked: "replayed"`).
A found ply is loaded from its files (`checked: "replayed"`). Pairs written or loaded are kept in a
bounded in-process LRU, keyed by the key and the digests of the bytes read, so the same bytes are
not replayed twice (CC-D C2).

Two processes may share the cache (AG-D §9): a reader holds the key's shared lock while it reads
the pair, a writer the exclusive lock while it checks again and writes it (`fcntl.flock` on
`<key>.lock`, one file per key, never removed).
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from calliope.facts import FactEngine, StoredTreeError
from calliope.reasoning import StoredGraphError
from calliope.reasoning.storage import load, save
from calliope.results import Bundle
from calliope.server.files import atomic_write, read_or_none

KEY_VERSION = "ply_key_v1"
CHECKED = ("written", "replayed")  # how a pair was checked (CC-D C5)
MAX_LOADED = 64  # kept pairs (CC-D §3.2, owner Q2)
MAX_LOADED_MB = 256  # estimated memory of the kept pairs
BYTES_PER_FILE_BYTE = 120  # the estimate: the largest ratio measured (CC-D §0.3, 0.118 MB per KB)


class StoreFailed(Exception):
    """A just-stored bundle failed its check (AS-D §3, CC-D §2.1): a defect."""


@dataclass(frozen=True, slots=True)
class Loaded:
    """A ply's analysis and rendered text with the bundle of their files. Shared, never copied:
    stored analyses are read-only (AG-D A6, CC-D §3.3)."""

    analysis: object  # Analysis: the pipeline's ("written") or replayed from the files
    rendered: object  # RenderedExplanation
    bundle: Bundle
    checked: str = "replayed"  # CHECKED (CC-D C5)


def canonical(value) -> bytes:
    """Compact UTF-8 JSON with sorted keys: the preimage of the cache key and the job id."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class PlyCache:
    def __init__(
        self,
        root: Path,
        *,
        verify_writes: bool = False,
        max_loaded: int = MAX_LOADED,
        max_loaded_mb: int = MAX_LOADED_MB,
    ) -> None:
        if max_loaded < 0 or max_loaded_mb < 0:
            raise ValueError("max_loaded and max_loaded_mb are at least 0 (0: nothing is kept)")
        self.root = root
        self.verify_writes = verify_writes
        self.max_loaded = max_loaded
        self.max_loaded_bytes = max_loaded_mb * 1024 * 1024
        self._kept: OrderedDict[tuple[str, str, str], tuple[Loaded, int]] = OrderedDict()
        self._kept_bytes = 0  # their estimated memory
        self._guard = threading.Lock()  # the LRU and the counts (CC-D §3.4)
        self.counts = {"written": 0, "replayed": 0, "reused": 0}

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

    @contextmanager
    def lock(self, key: str, *, exclusive: bool) -> Iterator[None]:
        """The key's inter-process lock (AG-D §9); a shared one is not taken on a key whose folder
        does not exist yet (nothing to read)."""

        tree_path, _ = self.paths(key)
        if exclusive:
            tree_path.parent.mkdir(parents=True, exist_ok=True)
        elif not tree_path.parent.is_dir():
            yield
            return
        with open(tree_path.parent / f"{key}.lock", "a+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def get(self, key: str, expected, build) -> Loaded | None:
        """The stored ply, or None on a miss (AS-D §4, review B2): a missing or unreadable file,
        a tree or graph that fails to load, or another request or build."""

        with self.lock(key, exclusive=False):
            return self._get(key, expected, build)

    def _get(self, key: str, expected, build) -> Loaded | None:
        """Under the key's lock: the bytes read are one generation of the pair (CC-D §3.1)."""

        tree_path, graph_path = self.paths(key)
        graph = read_or_none(graph_path)  # written last: present means the pair was complete
        tree = read_or_none(tree_path) if graph is not None else None
        if tree is None or graph is None:
            return None
        bundle = _bundle(tree, graph)
        kept = self._kept_pair(key, bundle)
        if kept is not None and _matches(kept.analysis, expected, build):
            with self._guard:
                self.counts["reused"] += 1
            return kept
        try:
            analysis, rendered = load(FactEngine(), tree, graph)
        except (StoredTreeError, StoredGraphError):
            return None
        if not _matches(analysis, expected, build):
            return None
        loaded = Loaded(analysis, rendered, bundle, "replayed")
        self._keep(key, loaded, len(tree) + len(graph), "replayed")
        return loaded

    def put(self, key: str, analysis, rendered, expected, build) -> Loaded:
        """Store a just-analysed ply (`_put`, CC-D §2.1). Under the key's exclusive lock; a sound
        pair another process wrote meanwhile is used as it is (AG-D §9)."""

        with self.lock(key, exclusive=True):
            found = self._get(key, expected, build)
            if found is not None:
                return found
            return self._put(key, analysis, rendered, expected, build)

    def _put(self, key: str, analysis, rendered, expected, build) -> Loaded:
        """CC-D §2.1: save, write (tree first, graph last), read both back and compare the bytes,
        check the request and build; with `verify_writes`, also load the bytes back and save them
        again (AS-D §3 as before). Any failure removes both files."""

        tree, graph = save(analysis, rendered)
        tree_path, graph_path = self.paths(key)
        atomic_write(tree_path, tree)
        atomic_write(graph_path, graph)
        checked = "replayed" if self.verify_writes else "written"
        try:
            back_tree, back_graph = tree_path.read_bytes(), graph_path.read_bytes()
            if (back_tree, back_graph) != (tree, graph):
                raise StoreFailed("the files read back are not the bytes written")
            if self.verify_writes:
                analysis, rendered = load(FactEngine(), back_tree, back_graph)
                if save(analysis, rendered) != (tree, graph):
                    raise StoreFailed("the re-loaded analysis saves to other bytes")
            if not _matches(analysis, expected, build):
                raise StoreFailed("the stored request or build is not the expected one")
        except (OSError, StoredTreeError, StoredGraphError, StoreFailed) as error:
            graph_path.unlink(missing_ok=True)
            tree_path.unlink(missing_ok=True)
            raise StoreFailed(f"{type(error).__name__}: {error}") from error
        loaded = Loaded(analysis, rendered, _bundle(tree, graph), checked)
        self._keep(key, loaded, len(tree) + len(graph), checked)
        return loaded

    # -- the kept pairs (CC-D C2) ----------------------------------------------------------------

    def _kept_pair(self, key: str, bundle: Bundle) -> Loaded | None:
        with self._guard:
            entry = self._kept.get((key, bundle.tree, bundle.graph))
            if entry is None:
                return None
            self._kept.move_to_end((key, bundle.tree, bundle.graph))
            return entry[0]

    def _keep(self, key: str, loaded: Loaded, file_bytes: int, checked: str) -> None:
        """Count the pair and keep it, least recently used evicted until both bounds hold; a pair
        whose estimate alone passes the memory bound is not kept."""

        estimate = file_bytes * BYTES_PER_FILE_BYTE
        with self._guard:
            self.counts[checked] += 1
            if self.max_loaded == 0 or estimate > self.max_loaded_bytes:
                return
            name = (key, loaded.bundle.tree, loaded.bundle.graph)
            old = self._kept.pop(name, None)
            if old is not None:
                self._kept_bytes -= old[1]
            self._kept[name] = (loaded, estimate)
            self._kept_bytes += estimate
            while len(self._kept) > self.max_loaded or self._kept_bytes > self.max_loaded_bytes:
                _, (_, dropped) = self._kept.popitem(last=False)
                self._kept_bytes -= dropped

    def kept(self) -> dict:
        """How many pairs are kept and their estimated memory (CC-D §3.2)."""

        with self._guard:
            return {"pairs": len(self._kept), "estimated_bytes": self._kept_bytes}


def _matches(analysis, expected, build) -> bool:
    return analysis.round_zero.request == expected and analysis.build == build


def _bundle(tree: bytes, graph: bytes) -> Bundle:
    return Bundle(hashlib.sha256(tree).hexdigest(), hashlib.sha256(graph).hexdigest(), stored=True)
