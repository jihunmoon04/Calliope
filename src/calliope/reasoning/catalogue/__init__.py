"""Catalogue v1: the 21 hypothesis templates of R2-D, in registry order (R2-D §6).

The order is part of the build identity (R0-D §8.4); results do not depend on it (R0-D §6.3).
"""

from __future__ import annotations

from calliope.reasoning.catalogue.comparison import BetterMove
from calliope.reasoning.catalogue.functions import Forcing, OnlyMove, Prevents
from calliope.reasoning.catalogue.hanging import LeftEnPrise, NewlyUnsafe, RemovedDefender
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
    Forcing(),
    OnlyMove(),
    SacrificeOffer(),
    SacrificeSound(),
    SacrificeCompensated(),
    Prevents(),
    Fork(),
    Pin(),
    Skewer(),
    Discovery(),
    RemovedDefender(),
    NewlyUnsafe(),
    LeftEnPrise(),
    BetterMove(),
)

__all__ = ["CATALOGUE_V1"]
