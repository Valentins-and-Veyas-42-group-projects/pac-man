"""Messages emitted by cooperative analysis tasks."""

from dataclasses import dataclass
from typing import TypeAlias

from pacman.replay.models import ReplayId, Tick


@dataclass(frozen=True, slots=True)
class TurnObserved:
    """Example analysis output produced for a player turn."""

    replay_id: ReplayId
    tick: Tick


@dataclass(frozen=True, slots=True)
class DeathQueued:
    """Example analysis output requesting later death analysis."""

    replay_id: ReplayId
    tick: Tick


AnalysisMessage: TypeAlias = TurnObserved | DeathQueued
