"""Catalogue v1: the 21 hypothesis templates of R2-D, the three of LV-D, the one of MV-D, the one of
EA-D, the three of EV-D and the one of EF-D, in registry order (R2-D §6, LV-D §4.1, §6, MV-D §4,
EA-D §3, EV-D §5, EF-D §5; versions as of EF-D E5).

The order is part of the build identity (R0-D §8.4); results do not depend on it (R0-D §6.3).
"""

from __future__ import annotations

from calliope.reasoning.catalogue.comparison import (
    BestStopsReply,
    BetterAlternative,
    BetterMove,
    MissedGain,
)
from calliope.reasoning.catalogue.draws import ChecksDraw, ChecksDrawMissed
from calliope.reasoning.catalogue.exchange import CaptureHolds, PieceOffer, Rescue
from calliope.reasoning.catalogue.functions import CheckAnswer, Forcing, OnlyMove, Prevents
from calliope.reasoning.catalogue.hanging import LeftEnPrise, NewlyExposed, RemovedDefender
from calliope.reasoning.catalogue.material import MaterialGain, MaterialLoss
from calliope.reasoning.catalogue.mates import (
    MateAllowed,
    MateDelivered,
    MateFound,
    MateInOneAllowed,
    MateMissed,
)
from calliope.reasoning.catalogue.mechanisms import Discovery, Fork, Pin, Skewer
from calliope.reasoning.catalogue.sacrifice import (
    SacrificeCompensated,
    SacrificeOffer,
    SacrificeSound,
)

CATALOGUE_V1 = (
    MateDelivered(),
    MateFound(),
    MateInOneAllowed(),
    MateAllowed(),
    MateMissed(),
    MaterialLoss(),
    MaterialGain(),
    ChecksDraw(),
    Forcing(),
    CheckAnswer(),
    OnlyMove(),
    SacrificeOffer(),
    SacrificeSound(),
    SacrificeCompensated(),
    PieceOffer(),
    CaptureHolds(),
    Rescue(),
    Prevents(),
    Fork(),
    Pin(),
    Skewer(),
    Discovery(),
    RemovedDefender(),
    NewlyExposed(),
    LeftEnPrise(),
    BetterMove(),
    ChecksDrawMissed(),
    BestStopsReply(),
    MissedGain(),
    BetterAlternative(),
)

__all__ = ["CATALOGUE_V1"]
