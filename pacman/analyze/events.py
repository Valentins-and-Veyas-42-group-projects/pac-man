"""Typed factual events consumed by cooperative analysis tasks."""

from dataclasses import dataclass
from typing import TypeAlias

from pacman.replay.models import (
    CollectibleChange,
    Direction,
    Frame,
    Ghost,
    GhostState,
    ReplayId,
    Tick,
    TileIndex,
)


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


@dataclass(frozen=True, slots=True)
class FrameObserved:
    """One immutable replay frame became available for analysis."""

    replay_id: ReplayId
    frame: Frame


@dataclass(frozen=True, slots=True)
class CollectibleObserved:
    """One replay collectible transition became available."""

    replay_id: ReplayId
    change: CollectibleChange


@dataclass(frozen=True, slots=True)
class GhostStateChanged:
    """A ghost changed between chase, scatter, frightened, or eaten."""

    replay_id: ReplayId
    tick: Tick
    ghost: Ghost
    previous: GhostState
    current: GhostState


@dataclass(frozen=True, slots=True)
class BatchFinished:
    """Every factual event through one batch tick was published."""

    replay_id: ReplayId
    tick: Tick


AnalysisEvent: TypeAlias = (
    FrameObserved
    | CollectibleObserved
    | PlayerTurned
    | GhostStateChanged
    | DeathStarted
    | BatchFinished
)


def event_tick(event: AnalysisEvent) -> Tick:
    """Return the replay tick carried by any analysis event.

    Returns:
        Tick used by deterministic scheduler ordering.
    """
    if isinstance(event, FrameObserved):
        return event.frame.tick
    if isinstance(event, CollectibleObserved):
        return event.change.tick
    return event.tick
