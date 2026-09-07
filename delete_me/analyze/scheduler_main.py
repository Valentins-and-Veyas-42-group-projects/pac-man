"""Interactive playground for the generator-based analysis scheduler."""

from pacman.analyze.events import DeathStarted, PlayerTurned
from pacman.analyze.messages import DeathQueued, TurnObserved
from pacman.analyze.runtime.loop import AnalysisLoop
from pacman.analyze.runtime.operations import Emit, WaitForEvent
from pacman.analyze.runtime.task import AnalyzerGenerator
from pacman.replay.models import Direction, ReplayId, Tick, TileIndex
from typed_errs import Err, Nothing, Some


def turn_analyzer() -> AnalyzerGenerator:
    """Observe every player-turn event and emit one message per turn.

    Yields:
        Scheduler operations for waiting and emitting.
    """
    while True:
        received = yield WaitForEvent(PlayerTurned)
        if isinstance(received, Nothing):
            continue
        event = received.value
        if isinstance(event, PlayerTurned):
            yield Emit(TurnObserved(event.replay_id, event.tick))


def death_analyzer() -> AnalyzerGenerator:
    """Observe every death event and emit one queued-analysis message.

    Yields:
        Scheduler operations for waiting and emitting.
    """
    while True:
        received = yield WaitForEvent(DeathStarted)
        if isinstance(received, Some) and isinstance(received.value, DeathStarted):
            event = received.value
            yield Emit(DeathQueued(event.replay_id, event.tick))


def run() -> int:
    """Publish fake events through two independent generator tasks.

    Returns:
        Zero on success or one if a task fails.
    """
    loop = AnalysisLoop.create()
    turn_task = loop.spawn(turn_analyzer())
    death_task = loop.spawn(death_analyzer())

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

    print(f"spawned tasks: turn={int(turn_task)} death={int(death_task)}")
    for event in events:
        awakened = loop.publish(event)
        result = loop.run_ready(step_budget=10)
        if isinstance(result, Err):
            result.print_diagnostic()
            return 1
        print(
            f"published {type(event).__name__:<12} awakened={awakened} "
            f"steps={result.value.steps} ready={result.value.remaining_ready}"
        )
        for message in loop.drain_messages():
            print(f"  emitted {type(message).__name__} tick={int(message.tick)}")

    return 0
