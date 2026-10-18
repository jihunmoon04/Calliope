"""Handles (AG-D §3.6, AG4-D §3.3): every citable item an answer serves carries `"ref"`.

A handle names its kind (`j` a judgement, `c` a claim, `f` a fact record, `s` a search line, `x`
an explored line, `b` a board item — MS-D §6), its number and the process: `c3.<24 hex digits>` (a 96-bit token, review C10).
It is bound to its source — the game key, then a stored analysis (the path to the ply, its bundle's
digests, the reasoning build), the facts tree (its revision) or a search (its position and search)
— and to the item's address. The same item served again gets the same handle (review N1).

Handles are grouped by game: `drop` forgets a game's when the game is evicted. A handle is then
judged without its entry (review C8): another process's token, a number never issued, or one
issued and gone (`HandleExpired`).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from calliope.server import canonical

# `b` a board item (MS-D §6)
KINDS = {"j": "judgement", "c": "claim", "f": "fact", "s": "search_line", "x": "explored_line",
         "b": "board_item"}  # fmt: skip
_REF = re.compile(r"([a-z])(\d+)\.([0-9a-f]+)")


def is_handle(value) -> bool:
    """Whether a value is written as a handle (`c3.<hex>`), whichever process served it."""

    return isinstance(value, str) and _REF.fullmatch(value) is not None


class HandleError(LookupError):
    """A handle this process did not serve, or one cited for another game."""


class HandleExpired(HandleError):
    """A handle this process served whose game was put away or whose analysis is gone."""


@dataclass(frozen=True, slots=True)
class Entry:
    ref: str
    kind: str
    game: str  # the game key
    source: dict
    address: dict
    item: object  # what was served (JSON)


class Handles:
    def __init__(self, token: str | None = None) -> None:
        self.token = token if token is not None else secrets.token_hex(12)
        self._entries: dict[str, Entry] = {}
        self._by_game: dict[str, dict[bytes, str]] = {}  # game key -> item key -> ref
        self._issued = dict.fromkeys(KINDS, 0)  # per kind, the highest number issued

    def serve(self, prefix: str, game: str, source: dict, address: dict, item) -> str:
        """The item's handle: the existing one when this item was served before."""

        if prefix not in KINDS:
            raise ValueError(f"no handle kind {prefix!r}")
        key = canonical([prefix, source, address])
        served = self._by_game.setdefault(game, {})
        ref = served.get(key)
        if ref is not None:
            return ref
        self._issued[prefix] += 1
        ref = f"{prefix}{self._issued[prefix]}.{self.token}"
        self._entries[ref] = Entry(ref, KINDS[prefix], game, source, address, item)
        served[key] = ref
        return ref

    def fresh(self, game: str, keys) -> int:
        """How many distinct (prefix, source, address) of `keys` have no handle yet (review B1)."""

        served = self._by_game.get(game, {})
        return len({canonical(list(key)) for key in keys} - served.keys())

    def resolve(self, ref: str, game: str | None = None) -> Entry:
        entry = self._entries.get(ref)
        if entry is None:
            found = _REF.fullmatch(ref)
            if found is not None and found[3] != self.token:
                raise HandleError(f"{ref} was not served in this session")
            if found is None or found[1] not in KINDS or int(found[2]) > self._issued[found[1]]:
                raise HandleError(f"no handle {ref}: not a handle this server served")
            raise HandleExpired(f"{ref} expired: the game was put away or its analysis is gone; "
                                "read it again with ply/facts/explore")  # fmt: skip
        if game is not None and entry.game != game:
            raise HandleError(f"{ref} belongs to another game")
        return entry

    def count(self, game: str) -> int:
        return len(self._by_game.get(game, ()))

    def drop(self, game: str) -> None:
        """Forget every handle of a game (its eviction)."""

        for ref in self._by_game.pop(game, {}).values():
            del self._entries[ref]

    def __len__(self) -> int:
        return len(self._entries)
