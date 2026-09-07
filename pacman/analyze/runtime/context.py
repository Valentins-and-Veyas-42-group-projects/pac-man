"""User-facing operations available inside analysis coroutines."""

from pacman.analyze.messages import AnalysisMessage
from pacman.analyze.runtime.awaitables import (
    CooperativeYield,
    EmitMessage,
    EventT,
    NextEvent,
    SleepUntilTick,
    SpawnCoroutine,
)
from pacman.analyze.runtime.operations import AnalyzerCoroutine
from pacman.replay.models import Tick


class AnalysisContext:
    """Construct awaitables consumed by the custom scheduler."""

    def next_event(
        self,
        event_type: type[EventT],
    ) -> NextEvent[EventT]:
        """Wait for the next concrete event type.

        Returns:
            Typed event awaitable.
        """
        return NextEvent(event_type)

    def sleep_until(
        self,
        tick: Tick,
    ) -> SleepUntilTick:
        """Wait until one deterministic replay tick.

        Returns:
            Tick sleep awaitable.
        """
        return SleepUntilTick(tick)

    def emit(
        self,
        message: AnalysisMessage,
    ) -> EmitMessage:
        """Emit one analysis message.

        Returns:
            Message emission awaitable.
        """
        return EmitMessage(message)

    def yield_now(self) -> CooperativeYield:
        """Return control to other ready tasks.

        Returns:
            Cooperative yield awaitable.
        """
        return CooperativeYield()

    def spawn(self, coroutine: AnalyzerCoroutine) -> SpawnCoroutine:
        """Schedule one child coroutine.

        Returns:
            Child-spawn awaitable.
        """
        return SpawnCoroutine(coroutine)
