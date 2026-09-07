from pacman.analyze.events import PlayerTurned
from pacman.analyze.messages import TurnObserved
from pacman.analyze.runtime.context import AnalysisContext
from pacman.analyze.runtime.loop import AnalysisLoop
from pacman.replay.models import Direction, ReplayId, Tick, TileIndex


def turn(tick: int) -> PlayerTurned:
    return PlayerTurned(
        ReplayId(1),
        Tick(tick),
        TileIndex(4),
        Direction.RIGHT,
        Direction.DOWN,
    )


async def observe_one_turn(ctx: AnalysisContext) -> None:
    event = await ctx.next_event(PlayerTurned)
    await ctx.emit(TurnObserved(event.replay_id, event.tick))


async def emit_once(ctx: AnalysisContext, tick: int) -> None:
    await ctx.emit(TurnObserved(ReplayId(1), Tick(tick)))


async def spawn_child(ctx: AnalysisContext) -> None:
    await ctx.spawn(emit_once(ctx, 40))


async def cooperative_pair(
    ctx: AnalysisContext,
    first: int,
    second: int,
) -> None:
    await ctx.emit(TurnObserved(ReplayId(1), Tick(first)))
    await ctx.yield_now()
    await ctx.emit(TurnObserved(ReplayId(1), Tick(second)))


def test_native_coroutine_suspends_inside_custom_awaitable() -> None:
    loop = AnalysisLoop.create()
    coroutine = observe_one_turn(AnalysisContext())
    loop.spawn(coroutine)

    loop.run_ready(1).unwrap()

    assert coroutine.cr_await is not None
    assert loop.publish(turn(10)) == 1
    loop.run_ready(10).unwrap()
    assert loop.drain_messages() == (TurnObserved(ReplayId(1), Tick(10)),)


def test_coroutine_can_spawn_child_coroutine() -> None:
    loop = AnalysisLoop.create()
    loop.spawn(spawn_child(AnalysisContext()))

    loop.run_ready(10).unwrap()

    assert loop.drain_messages() == (TurnObserved(ReplayId(1), Tick(40)),)


def test_yield_now_interleaves_ready_coroutines() -> None:
    loop = AnalysisLoop.create()
    ctx = AnalysisContext()
    loop.spawn(cooperative_pair(ctx, 1, 3))
    loop.spawn(cooperative_pair(ctx, 2, 4))

    loop.run_ready(20).unwrap()

    assert loop.drain_messages() == (
        TurnObserved(ReplayId(1), Tick(1)),
        TurnObserved(ReplayId(1), Tick(2)),
        TurnObserved(ReplayId(1), Tick(3)),
        TurnObserved(ReplayId(1), Tick(4)),
    )
