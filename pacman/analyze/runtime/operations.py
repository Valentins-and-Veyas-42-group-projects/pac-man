"""Operations yielded by cooperative analysis generators."""

from dataclasses import dataclass
from typing import TypeAlias

from pacman.analyze.events import AnalysisEvent
from pacman.analyze.messages import AnalysisMessage


@dataclass(frozen=True, slots=True)
class WaitForEvent:
    """Suspend a task until an event of the requested type is published."""

    event_type: type[AnalysisEvent]


@dataclass(frozen=True, slots=True)
class Emit:
    """Publish one analysis result message."""

    message: AnalysisMessage


Operation: TypeAlias = WaitForEvent | Emit
