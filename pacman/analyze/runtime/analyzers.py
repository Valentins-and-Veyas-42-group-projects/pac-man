"""Small long-lived analyzers driven by factual replay events."""

from pacman.analyze.events import DeathStarted, PlayerTurned
from pacman.analyze.messages import (
    DeathQueued,
    DecisionEvaluationQueued,
    TurnObserved,
)
from pacman.analyze.runtime.context import AnalysisContext
from pacman.replay.models import Tick


async def observe_turns(context: AnalysisContext) -> None:
    """Emit one message for every observed player turn."""
    while True:
        turn = await context.next_event(PlayerTurned)
        await context.emit(TurnObserved(turn.replay_id, turn.tick))


async def queue_deaths(context: AnalysisContext) -> None:
    """Request deeper analysis whenever a death transition is observed."""
    while True:
        death = await context.next_event(DeathStarted)
        await context.emit(DeathQueued(death.replay_id, death.tick))


async def queue_turn_evaluation(
    context: AnalysisContext,
    turn: PlayerTurned,
    delay_ticks: int = 30,
) -> None:
    """Wait for the outcome window, then request decision evaluation."""
    evaluation_tick = Tick(int(turn.tick) + delay_ticks)

    await context.sleep_until(evaluation_tick)
    await context.emit(
        DecisionEvaluationQueued(
            replay_id=turn.replay_id,
            decision_tick=turn.tick,
            evaluation_tick=evaluation_tick,
        )
    )


async def schedule_turn_evaluations(
    context: AnalysisContext,
) -> None:
    """Schedule an independent delayed evaluation for every turn."""
    while True:
        turn = await context.next_event(PlayerTurned)
        await context.spawn(queue_turn_evaluation(context, turn))
