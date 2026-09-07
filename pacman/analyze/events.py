"""Typed factual events consumed by cooperative analysis tasks."""

from dataclasses import dataclass
from typing import TypeAlias

from pacman.replay.models import Direction, ReplayId, Tick, TileIndex


@dataclass(frozen=True, slots=True)
class PlayerTurned:
    """Pac-Man selected a different movement direction."""

    replay_id: ReplayId
    tick: Tick
    tile: TileIndex
    previous: Direction
    current: Direction


@dataclass(frozen=True, slots=True)
class DeathStarted:
    """A replay entered its death phase."""

    replay_id: ReplayId
    tick: Tick


AnalysisEvent: TypeAlias = PlayerTurned | DeathStarted
