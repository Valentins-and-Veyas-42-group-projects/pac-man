from collections.abc import Generator

from pacman.analyze.events import DeathStarted, PlayerTurned
from pacman.analyze.messages import DeathQueued, TurnObserved
from pacman.analyze.runtime.loop import AnalysisLoop
from pacman.analyze.runtime.operations import Emit, Operation, WaitForEvent
from pacman.analyze.runtime.task import AnalyzerGenerator
from pacman.replay.models import Direction, ReplayId, Tick, TileIndex
from typed_errs import Option, Some


def turn_analyzer() -> AnalyzerGenerator:
    while True:
        received = yield WaitForEvent(PlayerTurned)
        if isinstance(received, Some) and isinstance(received.value, PlayerTurned):
            yield Emit(TurnObserved(received.value.replay_id, received.value.tick))


def death_analyzer() -> AnalyzerGenerator:
    received = yield WaitForEvent(DeathStarted)
    if isinstance(received, Some) and isinstance(received.value, DeathStarted):
        yield Emit(DeathQueued(received.value.replay_id, received.value.tick))


def noisy_analyzer() -> Generator[Operation, Option[PlayerTurned | DeathStarted], None]:
    while True:
        yield Emit(TurnObserved(ReplayId(1), Tick(1)))


def turn(tick: int = 10) -> PlayerTurned:
    return PlayerTurned(
        ReplayId(1),
        Tick(tick),
        TileIndex(4),
        Direction.RIGHT,
        Direction.DOWN,
    )


def test_matching_event_resumes_every_waiting_task() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(turn_analyzer())
    loop.spawn(turn_analyzer())
    loop.run_ready(10).unwrap()

    assert loop.publish(turn()) == 2
    loop.run_ready(10).unwrap()

    assert loop.drain_messages() == (
        TurnObserved(ReplayId(1), Tick(10)),
        TurnObserved(ReplayId(1), Tick(10)),
    )


def test_unrelated_event_does_not_resume_waiter() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(turn_analyzer())
    loop.run_ready(10).unwrap()

    assert loop.publish(DeathStarted(ReplayId(1), Tick(10))) == 0
    assert loop.drain_messages() == ()


def test_completed_task_is_removed_from_future_events() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(death_analyzer())
    loop.run_ready(10).unwrap()
    loop.publish(DeathStarted(ReplayId(1), Tick(20)))
    loop.run_ready(10).unwrap()

    assert loop.drain_messages() == (DeathQueued(ReplayId(1), Tick(20)),)
    assert loop.publish(DeathStarted(ReplayId(1), Tick(21))) == 0


def test_step_budget_leaves_fair_work_for_later() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(noisy_analyzer())

    first = loop.run_ready(3).unwrap()

    assert first.steps == 3
    assert first.remaining_ready == 1
    assert len(loop.drain_messages()) == 3


def test_zero_step_budget_performs_no_work() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(turn_analyzer())

    result = loop.run_ready(0).unwrap()

    assert result.steps == 0
    assert result.remaining_ready == 1
