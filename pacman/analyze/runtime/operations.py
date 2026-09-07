"""Operations yielded by cooperative analysis generators."""

from collections.abc import Coroutine
from dataclasses import dataclass
from typing import TypeAlias

from pacman.analyze.events import AnalysisEvent
from pacman.analyze.messages import AnalysisMessage
from pacman.replay.models import Tick


@dataclass(frozen=True, slots=True)
class Operation:
    """Base type for every operation understood by the scheduler."""


AnalyzerCoroutine: TypeAlias = Coroutine[object, object, None]


@dataclass(frozen=True, slots=True)
class WaitForEvent(Operation):
    """Suspend until the scheduler publishes one concrete event type."""

    event_type: type[AnalysisEvent]


@dataclass(frozen=True, slots=True)
class Emit(Operation):
    """Append one analysis message to the scheduler output."""

    message: AnalysisMessage


@dataclass(frozen=True, slots=True)
class SleepUntil(Operation):
    """Suspend until the deterministic replay clock reaches a tick."""

    tick: Tick


@dataclass(frozen=True, slots=True)
class Spawn(Operation):
    """Register a child analyzer coroutine with the scheduler."""

    coroutine: AnalyzerCoroutine


@dataclass(frozen=True, slots=True)
class YieldNow(Operation):
    """Return the current task to the back of the ready queue."""

    pass
