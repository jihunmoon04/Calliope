"""Handles (AG-D §3.6): every citable item an answer serves carries `"ref"`.

A handle names its kind (`j` a judgement, `c` a claim, `f` a fact record, `s` a search line, `x`
an explored line), its number and the session: `c3.k7f2a9`. It is bound to its source — the game
key, then a stored analysis (the path to the ply, its bundle's digests, the reasoning build), the
facts tree (its revision) or a search (its position and search) — and to the item's address. A
handle resolves only in the session that served it, for the game it was served for.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

KINDS = {"j": "judgement", "c": "claim", "f": "fact", "s": "search_line", "x": "explored_line"}


class HandleError(LookupError):
    """A handle this session did not serve, or one cited for another game."""


@dataclass(frozen=True, slots=True)
class Entry:
    ref: str
    kind: str
    game: str  # the game key
    source: dict
    address: dict
    item: object  # what was served (JSON)


class Handles:
    def __init__(self, session: str | None = None) -> None:
        self.session = session if session is not None else secrets.token_hex(3)
        self._entries: dict[str, Entry] = {}
        self._next = dict.fromkeys(KINDS, 0)

    def serve(self, prefix: str, game: str, source: dict, address: dict, item) -> str:
        if prefix not in KINDS:
            raise ValueError(f"no handle kind {prefix!r}")
        self._next[prefix] += 1
        ref = f"{prefix}{self._next[prefix]}.{self.session}"
        self._entries[ref] = Entry(ref, KINDS[prefix], game, source, address, item)
        return ref

    def resolve(self, ref: str, game: str | None = None) -> Entry:
        entry = self._entries.get(ref)
        if entry is None:
            owner = ref.rpartition(".")[2]
            if owner and owner != self.session:
                raise HandleError(f"{ref} was not served in this session")
            raise HandleError(f"no handle {ref}")
        if game is not None and entry.game != game:
            raise HandleError(f"{ref} belongs to another game")
        return entry

    def __len__(self) -> int:
        return len(self._entries)
