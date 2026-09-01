"""Unit tests for replay recorder batching."""

import asyncio

from pacman.replay.models import (
    Collectible,
    CollectibleChange,
    Coord,
    Direction,
    Frame,
    FrameBatch,
    GamePhase,
    PlayerFrame,
    Position,
    ReplayId,
    Score,
    Tick,
    TileIndex,
)
from pacman.replay.recorder import Recorder
from pacman.replay.writer import Append, Finish, WriterCommand
from typed_concurrency import Channel
from typed_errs import Some


async def receive(channel: Channel[WriterCommand]) -> WriterCommand:
    """Receive one command from a channel known to contain a value."""
    result = await channel.recv()
    assert isinstance(result, Some)
    return result.value


def test_flushes_exactly_at_buffer_size() -> None:
    """The frame reaching capacity is included in the dispatched batch."""

    async def exercise() -> None:
        channel = Channel[WriterCommand]()
        recorder = Recorder(ReplayId(7), channel, buf_size=2)

        await recorder.on_frame(replay_frame(0))
        assert channel._queue.empty()

        await recorder.on_frame(replay_frame(1))
        assert await receive(channel) == Append(
            batch=recorder_batch(ReplayId(7), (replay_frame(0), replay_frame(1)))
        )

    asyncio.run(exercise())


def test_finish_flushes_partial_batch_before_finish() -> None:
    """Finishing preserves the final partial batch and command ordering."""

    async def exercise() -> None:
        channel = Channel[WriterCommand]()
        recorder = Recorder(ReplayId(8), channel, buf_size=3)
        change = CollectibleChange(Tick(1), TileIndex(2), Collectible.NONE)

        await recorder.on_frame(replay_frame(0))
        await recorder.on_frame(replay_frame(1))
        recorder.on_collectible_change(change)
        await recorder.finish()

        assert await receive(channel) == Append(
            batch=recorder_batch(
                ReplayId(8),
                (replay_frame(0), replay_frame(1)),
                (change,),
            )
        )
        assert await receive(channel) == Finish(ReplayId(8))

    asyncio.run(exercise())


def test_flushes_collectible_changes_without_frames() -> None:
    """World changes are not stranded when no frame is buffered."""

    async def exercise() -> None:
        channel = Channel[WriterCommand]()
        recorder = Recorder(ReplayId(9), channel)
        change = CollectibleChange(Tick(0), TileIndex(0), Collectible.NONE)
        recorder.on_collectible_change(change)

        await recorder.flush()

        assert await receive(channel) == Append(batch=recorder_batch(ReplayId(9), (), (change,)))

    asyncio.run(exercise())


def test_empty_flush_dispatches_nothing() -> None:
    """An empty recorder does not create an empty database transaction."""

    async def exercise() -> None:
        channel = Channel[WriterCommand]()
        recorder = Recorder(ReplayId(10), channel)
        await recorder.flush()
        assert channel._queue.empty()

    asyncio.run(exercise())


def recorder_batch(
    replay_id: ReplayId,
    frames: tuple[Frame, ...],
    changes: tuple[CollectibleChange, ...] = (),
) -> FrameBatch:
    """Build an expected batch without repeating its constructor inline."""
    return FrameBatch(replay_id, frames, changes)


def replay_frame(tick: int) -> Frame:
    """Build a small frame for recorder tests."""
    return Frame(
        tick=Tick(tick),
        player=PlayerFrame(Position(Coord(tick), Coord(0)), Direction.RIGHT),
        ghosts=(),
        score=Score(tick * 10),
        lives=3,
        phase=GamePhase.PLAYING,
    )
