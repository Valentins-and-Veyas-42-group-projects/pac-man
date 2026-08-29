# uv run python -m delete_me.analyze.live_main
# Made by Codex as a disposable live-analysis pipeline runner.

"""Demonstrate non-blocking replay persistence and analysis fan-out."""

import asyncio

from pacman.replay.models import (
    Coord,
    Direction,
    Frame,
    FrameBatch,
    GamePhase,
    Ghost,
    GhostFrame,
    GhostState,
    PlayerFrame,
    Position,
    ReplayId,
    Score,
    Tick,
)
from typed_concurrency import Group

from delete_me.analyze.live import (
    AnalysisOffer,
    BoundedAnalysisQueue,
    MockAnalysisWorker,
    MockLiveReplayAnalyzer,
)


def mock_history(replay_id: ReplayId) -> FrameBatch:
    """Create a small head-on history for pipeline wiring.

    Returns:
        An immutable replay batch ending in a death transition.
    """
    frames: list[Frame] = []
    for tick, pac_x, blinky_x, phase in (
        (100, 10, 14, GamePhase.PLAYING),
        (101, 11, 13, GamePhase.PLAYING),
        (102, 12, 12, GamePhase.PLAYING),
        (103, 12, 12, GamePhase.DYING),
    ):
        frames.append(
            Frame(
                Tick(tick),
                PlayerFrame(
                    Position(Coord(pac_x), Coord(10)),
                    Direction.RIGHT,
                ),
                (
                    GhostFrame(
                        Ghost.BLINKY,
                        Position(Coord(blinky_x), Coord(10)),
                        Direction.LEFT,
                        GhostState.CHASE,
                    ),
                ),
                Score(0),
                3,
                phase,
            )
        )
    return FrameBatch(replay_id, tuple(frames), ())


def split_frames(batch: FrameBatch) -> tuple[FrameBatch, ...]:
    """Split a history into one-frame producer batches.

    Returns:
        Immutable batches that preserve the original replay identity.
    """
    return tuple(FrameBatch(batch.replay_id, (frame,), ()) for frame in batch.frames)


async def run() -> int:
    """Fan one history out to persistence and incremental analysis.

    Returns:
        Zero after both consumers see the intended data.
    """
    replay_id = ReplayId(1)
    history = mock_history(replay_id)
    persisted: list[FrameBatch] = []
    queue = BoundedAnalysisQueue(capacity=len(history.frames))
    analyzer = MockLiveReplayAnalyzer(replay_id)
    worker = MockAnalysisWorker(queue, analyzer)
    offers: list[AnalysisOffer] = []

    async with Group() as group:
        group << worker.run()
        for batch in split_frames(history):
            persisted.append(batch)
            offers.append(queue.offer(batch))
        await queue.close()

    if any(offer is not AnalysisOffer.ACCEPTED for offer in offers):
        print("unexpected analysis backfill in the no-pressure demo")
        return 1

    pressure_queue = BoundedAnalysisQueue(capacity=1)
    batches = split_frames(history)
    first_offer = pressure_queue.offer(batches[0])
    overflow_offer = pressure_queue.offer(batches[1])
    if (
        first_offer is not AnalysisOffer.ACCEPTED
        or overflow_offer is not AnalysisOffer.NEEDS_BACKFILL
        or len(pressure_queue.backfills) != 1
    ):
        print("bounded queue did not preserve the overflow backfill range")
        return 1

    print("GAME / RECORDER")
    print(f"  batches produced:   {len(persisted)}")
    print("          | same immutable FrameBatch")
    print("          +-------------------------+")
    print("          v                         v")
    print("REPLAY PERSISTENCE             ANALYSIS WORKER")
    print(f"  batches accepted:   {len(persisted)}")
    print(f"  observations:       {len(analyzer.observations)}")
    print(f"  candidate moments:  {len(analyzer.moments)}")
    print(f"  deep jobs:          {len(analyzer.jobs)}")
    print(f"  backfill ranges:    {len(queue.backfills)}")
    print("  overflow policy:    non-blocking, persisted range marked for backfill")
    print()
    for moment in analyzer.moments:
        print(f"moment tick {moment.tick}: {moment.kind.value}")
    for job in analyzer.jobs:
        print(f"job {job.priority.name}: {job.kind.value} ticks {job.start_tick}..{job.end_tick}")
    return 0


def main() -> None:
    """Run the disposable live-analysis pipeline demonstration.

    Raises:
        SystemExit: With the pipeline demonstration status.
    """
    try:
        raise SystemExit(asyncio.run(run()))
    except (KeyboardInterrupt, Exception) as error:
        print(f"live-analyze-dev failed unexpectedly: {error}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
