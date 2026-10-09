"""Engine profile, identity and pinned options (F4-D §3.2)."""

from __future__ import annotations

from dataclasses import dataclass, fields

from calliope.facts.errors import InvalidRequestError

SUPPORTED_ENGINE = "Stockfish 19"  # exact UCI `id name`; another engine re-passes F4-D §9.3


@dataclass(frozen=True, slots=True)
class EngineProfile:
    """What every search of a session asks the engine for. WDL is always requested if offered."""

    name: str = "d12_mpv5_v1"
    depth: int = 12
    time_cap_ms: int = 2000
    multipv: int = 5
    threads: int = 1
    hash_mb: int = 16

    def __post_init__(self) -> None:
        if self.threads != 1:
            raise InvalidRequestError("only threads=1 searches are deterministic (F4-D M2)")
        if self.depth < 1 or self.multipv < 1 or self.time_cap_ms < 1 or self.hash_mb < 1:
            raise InvalidRequestError("profile depth, multipv, time cap and hash must be positive")

    def fingerprint(self) -> tuple[str, ...]:
        return tuple(f"{f.name}={getattr(self, f.name)}" for f in fields(self))


@dataclass(frozen=True, slots=True)
class EngineOption:
    name: str
    type: str
    default: str | None  # None for buttons


@dataclass(frozen=True, slots=True)
class EngineIdentity:
    name: str
    author: str
    binary_sha256: str
    options: tuple[EngineOption, ...]  # as offered, in the engine's order

    def offers(self, option: str) -> bool:
        return any(o.name == option for o in self.options)

    def default(self, option: str) -> str | None:
        return next((o.default for o in self.options if o.name == option), None)

    def fingerprint(self) -> tuple[str, ...]:
        return (
            f"name={self.name}",
            f"author={self.author}",
            f"sha256={self.binary_sha256}",
            *(f"option={o.name}|{o.type}|{o.default}" for o in self.options),
        )


PinnedOptions = tuple[tuple[str, str], ...]


def start_options(identity: EngineIdentity) -> PinnedOptions:
    """Sent once when the port starts: the expensive options (F4-D §3.2, M11)."""

    out: list[tuple[str, str]] = [("Threads", "1")]
    evalfile = identity.default("EvalFile")
    if evalfile is not None:
        out.append(("EvalFile", evalfile))
    return tuple(out)


def search_options(identity: EngineIdentity, profile: EngineProfile, multipv: int) -> PinnedOptions:
    """Sent before every search, for every search-affecting option the engine offers."""

    wanted = (
        ("Hash", str(profile.hash_mb)),
        ("MultiPV", str(multipv)),
        ("UCI_ShowWDL", "true"),
        ("SyzygyPath", "<empty>"),
        ("Skill Level", "20"),
        ("UCI_LimitStrength", "false"),
        ("UCI_Elo", identity.default("UCI_Elo") or ""),
        ("nodestime", "0"),
        ("UCI_Chess960", "false"),
        ("Ponder", "false"),
    )
    return tuple((name, value) for name, value in wanted if identity.offers(name))
