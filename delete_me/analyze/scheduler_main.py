"""Interactive playground for the native-coroutine analysis scheduler."""

from pacman.analyze.events import DeathStarted, PlayerTurned
from pacman.analyze.messages import DeathQueued, TurnObserved
from pacman.analyze.runtime.context import AnalysisContext
from pacman.analyze.runtime.loop import AnalysisLoop
from pacman.replay.models import Direction, ReplayId, Tick, TileIndex
from typed_errs import Err


async def turn_analyzer(ctx: AnalysisContext) -> None:
    """Observe every player-turn event and emit one message per turn."""
    while True:
        event = await ctx.next_event(PlayerTurned)
        await ctx.emit(TurnObserved(event.replay_id, event.tick))


async def death_analyzer(ctx: AnalysisContext) -> None:
    """Observe every death event and emit one queued-analysis message."""
    while True:
        event = await ctx.next_event(DeathStarted)
        await ctx.emit(DeathQueued(event.replay_id, event.tick))


async def delayed_death_analyzer(ctx: AnalysisContext) -> None:
    """Emit death analysis thirty replay ticks after observing death."""
    death = await ctx.next_event(DeathStarted)
    await ctx.sleep_until(Tick(int(death.tick) + 30))
    await ctx.emit(DeathQueued(death.replay_id, death.tick))


def run() -> int:
    """Publish fake events through two independent generator tasks.

    Returns:
        Zero on success or one if a task fails.
    """
    loop = AnalysisLoop.create()
    ctx = AnalysisContext()
    turn_coroutine = turn_analyzer(ctx)
    turn_task = loop.spawn(turn_coroutine)
    death_task = loop.spawn(death_analyzer(ctx))
    delayed_task = loop.spawn(delayed_death_analyzer(ctx))

    started = loop.run_ready(step_budget=10)
    if isinstance(started, Err):
        started.print_diagnostic()
        return 1

    events = (
        PlayerTurned(
            ReplayId(7),
            Tick(100),
            TileIndex(12),
            Direction.RIGHT,
            Direction.DOWN,
        ),
        PlayerTurned(
            ReplayId(7),
            Tick(120),
            TileIndex(18),
            Direction.DOWN,
            Direction.LEFT,
        ),
        DeathStarted(ReplayId(7), Tick(150)),
    )

    print(
        f"spawned tasks: turn={int(turn_task)} death={int(death_task)} delayed={int(delayed_task)}"
    )
    print(
        f"native coroutine: {turn_coroutine.cr_code.co_name} "
        f"awaiting={type(turn_coroutine.cr_await).__name__}"
    )
    for event in events:
        advanced = loop.advance_to(event.tick)
        if isinstance(advanced, Err):
            advanced.print_diagnostic()
            return 1
        awakened = loop.publish(event)
        result = loop.run_ready(step_budget=10)
        if isinstance(result, Err):
            result.print_diagnostic()
            return 1
        print(
            f"published {type(event).__name__:<12} awakened={awakened} "
            f"steps={result.value.steps} ready={result.value.remaining_ready} "
            f"sleeping={loop.sleeping_count}"
        )
        for message in loop.drain_messages():
            print(f"  emitted {type(message).__name__} tick={int(message.tick)}")

    for tick in (Tick(179), Tick(180)):
        advanced = loop.advance_to(tick)
        if isinstance(advanced, Err):
            advanced.print_diagnostic()
            return 1
        result = loop.run_ready(step_budget=10)
        if isinstance(result, Err):
            result.print_diagnostic()
            return 1
        print(
            f"advanced tick={int(tick)} awakened={advanced.value} "
            f"steps={result.value.steps} sleeping={loop.sleeping_count}"
        )
        for message in loop.drain_messages():
            print(f"  delayed {type(message).__name__} original_tick={int(message.tick)}")

    return 0
