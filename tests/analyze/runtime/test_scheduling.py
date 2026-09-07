from pacman.analyze.messages import DeathQueued
from pacman.analyze.runtime.context import AnalysisContext
from pacman.analyze.runtime.loop import AnalysisLoop, LoopError
from pacman.replay.models import ReplayId, Tick
from typed_errs import Err


async def sleeper(ctx: AnalysisContext, replay_id: int, wake_tick: int) -> None:
    await ctx.sleep_until(Tick(wake_tick))
    await ctx.emit(DeathQueued(ReplayId(replay_id), Tick(wake_tick)))


def test_sleeping_task_wakes_at_exact_tick() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(sleeper(AnalysisContext(), 1, 30))
    loop.run_ready(10).unwrap()

    assert loop.sleeping_count == 1
    assert loop.advance_to(Tick(29)).unwrap() == 0
    assert loop.run_ready(10).unwrap().steps == 0
    assert loop.drain_messages() == ()

    assert loop.advance_to(Tick(30)).unwrap() == 1
    loop.run_ready(10).unwrap()
    assert loop.drain_messages() == (DeathQueued(ReplayId(1), Tick(30)),)


def test_advancing_past_deadline_wakes_task() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(sleeper(AnalysisContext(), 1, 20))
    loop.run_ready(10).unwrap()

    assert loop.advance_to(Tick(50)).unwrap() == 1


def test_clock_rejects_backwards_tick() -> None:
    loop = AnalysisLoop.create()
    loop.advance_to(Tick(20)).unwrap()

    result = loop.advance_to(Tick(19))

    assert isinstance(result, Err)
    assert result.error is LoopError.TICK_MOVED_BACKWARDS


def test_same_tick_tasks_wake_in_schedule_order() -> None:
    loop = AnalysisLoop.create()
    ctx = AnalysisContext()
    loop.spawn(sleeper(ctx, 1, 30))
    loop.spawn(sleeper(ctx, 2, 30))
    loop.run_ready(10).unwrap()

    assert loop.advance_to(Tick(30)).unwrap() == 2
    loop.run_ready(10).unwrap()

    assert loop.drain_messages() == (
        DeathQueued(ReplayId(1), Tick(30)),
        DeathQueued(ReplayId(2), Tick(30)),
    )
