"""End-to-end replay persistence and process-analysis pipeline test."""

import asyncio

from pacman.analyze.messages import DeathQueued, DecisionEvaluationQueued, TurnObserved
from pacman.analyze.simulation import SimulationRules
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import (
    Coord,
    Direction,
    Frame,
    GamePhase,
    Maze,
    MazeId,
    PlayerFrame,
    Position,
    ReplayId,
    Score,
    Tick,
)
from pacman.replay.pipeline import ReplayPipeline
from pacman.replay.store import ReplayStore
from typed_concurrency import Group


def pipeline_maze(maze_id: MazeId) -> Maze:
    """Build a five-tile corridor for deterministic movement."""
    return Maze(
        maze_id,
        5,
        1,
        encode_topology([[13, 5, 5, 5, 7]]).unwrap(),
        b"\x00\x00",
        b"pipeline-test",
    )


def frame(tick: int) -> Frame:
    """Move Pac-Man back and forth and die on the final simulated tick."""
    offset = tick % 8
    x = offset if offset <= 4 else 8 - offset
    direction = Direction.RIGHT if offset < 4 else Direction.LEFT
    phase = GamePhase.DYING if tick == 7_199 else GamePhase.PLAYING
    return Frame(
        Tick(tick),
        PlayerFrame(Position(Coord(x), Coord(0)), direction),
        (),
        Score(tick * 10),
        2 if phase is GamePhase.DYING else 3,
        phase,
    )


def test_two_minute_game_is_stored_and_analyzed(
    store: ReplayStore,
    replay: tuple[MazeId, ReplayId],
) -> None:
    """Push 120 seconds at 60 Hz through the real storage and IPC boundaries."""

    async def exercise() -> None:
        maze_id, replay_id = replay
        pipeline = ReplayPipeline.create(
            replay_id,
            store,
            pipeline_maze(maze_id),
            SimulationRules(),
            buffer_size=240,
            writer_capacity=4,
            analysis_capacity=32,
        ).unwrap()

        async with Group() as group:
            group << pipeline.run_storage()
            pipeline.start().unwrap()
            for tick in range(7_200):
                await pipeline.on_frame(frame(tick))
                if tick % 120 == 0:
                    pipeline.drain_analysis()
            report = (await pipeline.finish()).unwrap()

        assert report.frames == 7_200
        assert report.batches == 30
        assert report.analyzed_batches == 30
        assert report.rejected_offers == ()
        assert any(isinstance(message, TurnObserved) for message in report.messages)
        assert any(isinstance(message, DecisionEvaluationQueued) for message in report.messages)
        assert DeathQueued(replay_id, Tick(7_199)) in report.messages
        assert store.frame(replay_id, Tick(0)).unwrap() == frame(0)
        assert store.frame(replay_id, Tick(7_199)).unwrap() == frame(7_199)
        assert store.replay(replay_id).unwrap().ended_at is not None

    asyncio.run(exercise())
