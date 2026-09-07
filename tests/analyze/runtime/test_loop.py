from pacman.analyze.events import DeathStarted, PlayerTurned
from pacman.analyze.messages import DeathQueued, TurnObserved
from pacman.analyze.runtime.context import AnalysisContext
from pacman.analyze.runtime.loop import AnalysisLoop
from pacman.replay.models import Direction, ReplayId, Tick, TileIndex


async def turn_analyzer(ctx: AnalysisContext) -> None:
    while True:
        event = await ctx.next_event(PlayerTurned)
        await ctx.emit(TurnObserved(event.replay_id, event.tick))


async def death_analyzer(ctx: AnalysisContext) -> None:
    event = await ctx.next_event(DeathStarted)
    await ctx.emit(DeathQueued(event.replay_id, event.tick))


async def noisy_analyzer(ctx: AnalysisContext) -> None:
    while True:
        await ctx.emit(TurnObserved(ReplayId(1), Tick(1)))


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
    ctx = AnalysisContext()
    loop.spawn(turn_analyzer(ctx))
    loop.spawn(turn_analyzer(ctx))
    loop.run_ready(10).unwrap()

    assert loop.publish(turn()) == 2
    loop.run_ready(10).unwrap()

    assert loop.drain_messages() == (
        TurnObserved(ReplayId(1), Tick(10)),
        TurnObserved(ReplayId(1), Tick(10)),
    )


def test_unrelated_event_does_not_resume_waiter() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(turn_analyzer(AnalysisContext()))
    loop.run_ready(10).unwrap()

    assert loop.publish(DeathStarted(ReplayId(1), Tick(10))) == 0
    assert loop.drain_messages() == ()


def test_completed_task_is_removed_from_future_events() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(death_analyzer(AnalysisContext()))
    loop.run_ready(10).unwrap()
    loop.publish(DeathStarted(ReplayId(1), Tick(20)))
    loop.run_ready(10).unwrap()

    assert loop.drain_messages() == (DeathQueued(ReplayId(1), Tick(20)),)
    assert loop.publish(DeathStarted(ReplayId(1), Tick(21))) == 0


def test_step_budget_leaves_fair_work_for_later() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(noisy_analyzer(AnalysisContext()))

    first = loop.run_ready(3).unwrap()

    assert first.steps == 3
    assert first.remaining_ready == 1
    assert len(loop.drain_messages()) == 3


def test_zero_step_budget_performs_no_work() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(turn_analyzer(AnalysisContext()))

    result = loop.run_ready(0).unwrap()

    assert result.steps == 0
    assert result.remaining_ready == 1
    loop.run_ready(1).unwrap()
