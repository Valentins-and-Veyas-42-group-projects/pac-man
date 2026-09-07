"""Awaitables translated into operations for the custom analysis loop."""

from collections.abc import Generator
from dataclasses import dataclass
from typing import Generic, TypeVar

from typed_errs import Some

from pacman.analyze.events import AnalysisEvent
from pacman.analyze.messages import AnalysisMessage
from pacman.analyze.runtime.operations import (
    AnalyzerCoroutine,
    Emit,
    Operation,
    SleepUntil,
    Spawn,
    WaitForEvent,
    YieldNow,
)
from pacman.replay.models import Tick

EventT = TypeVar(
    "EventT",
    bound=AnalysisEvent,
)


@dataclass(frozen=True, slots=True)
class NextEvent(Generic[EventT]):
    """Await one concrete analysis event type."""

    event_type: type[EventT]

    def __await__(
        self,
    ) -> Generator[Operation, object, EventT]:
        """Yield an event wait and return the matching event.

        Returns:
            Matching event supplied by the scheduler.

        Yields:
            Operation understood by the analysis scheduler.

        Raises:
            RuntimeError: If the scheduler violates the waiter invariant.
        """
        received = yield WaitForEvent(self.event_type)

        if not isinstance(received, Some):
            raise RuntimeError("event waiter resumed without an event")

        event = received.value

        if not isinstance(event, self.event_type):
            raise RuntimeError("event waiter resumed with wrong event type")

        return event


@dataclass(frozen=True, slots=True)
class SleepUntilTick:
    """Await deterministic replay time."""

    tick: Tick

    def __await__(
        self,
    ) -> Generator[Operation, object, None]:
        """Yield a sleep operation.

        Yields:
            Operation understood by the analysis scheduler.
        """
        yield SleepUntil(self.tick)


@dataclass(frozen=True, slots=True)
class EmitMessage:
    """Await emission of one analysis message."""

    message: AnalysisMessage

    def __await__(
        self,
    ) -> Generator[Operation, object, None]:
        """Yield a message-emission operation.

        Yields:
            Operation understood by the analysis scheduler.
        """
        yield Emit(self.message)


@dataclass(frozen=True, slots=True)
class CooperativeYield:
    """Move the coroutine behind other ready tasks."""

    def __await__(
        self,
    ) -> Generator[Operation, object, None]:
        """Yield control to the scheduler.

        Yields:
            Operation understood by the analysis scheduler.
        """
        yield YieldNow()


@dataclass(frozen=True, slots=True)
class SpawnCoroutine:
    """Await registration of one child analysis coroutine."""

    coroutine: AnalyzerCoroutine

    def __await__(
        self,
    ) -> Generator[Operation, object, None]:
        """Yield a child-spawn operation.

        Yields:
            Operation understood by the analysis scheduler.
        """
        yield Spawn(self.coroutine)
