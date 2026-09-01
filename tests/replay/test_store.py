"""Unit tests for replay persistence and reconstruction."""

from pacman.replay.models import (
    Collectible,
    CollectibleChange,
    Coord,
    Direction,
    EncodedMaze,
    Frame,
    FrameBatch,
    GamePhase,
    Ghost,
    GhostFrame,
    GhostState,
    MazeId,
    PlayerFrame,
    Position,
    ReplayId,
    Score,
    Tick,
    TileIndex,
)
from pacman.replay.store import ReplayStore
from typed_errs import Err


def frame(tick: int = 0) -> Frame:
    """Build one representative replay frame."""
    return Frame(
        tick=Tick(tick),
        player=PlayerFrame(Position(Coord(0), Coord(1)), Direction.RIGHT),
        ghosts=(
            GhostFrame(
                Ghost.BLINKY,
                Position(Coord(1), Coord(0)),
                Direction.LEFT,
                GhostState.CHASE,
            ),
        ),
        score=Score(10),
        lives=3,
        phase=GamePhase.PLAYING,
    )


def test_maze_roundtrip(store: ReplayStore, maze: EncodedMaze) -> None:
    """Persisted encoded mazes load without loss."""
    maze_id = store.create_maze(maze).unwrap()
    assert store.maze(maze_id).unwrap() == maze


def test_replay_metadata_roundtrip_and_finish(
    store: ReplayStore, replay: tuple[MazeId, ReplayId]
) -> None:
    """Replay metadata loads and records completion."""
    maze_id, replay_id = replay
    metadata = store.replay(replay_id).unwrap()
    assert metadata.maze_id == maze_id
    assert metadata.tick_hz == 60
    assert metadata.level == 1
    assert metadata.simulation_version == 2
    assert metadata.config_hash == b"config-hash"
    assert metadata.rng_seed == 42
    assert metadata.ended_at is None

    store.finish(replay_id).unwrap()
    assert store.replay(replay_id).unwrap().ended_at is not None


def test_frame_roundtrip(store: ReplayStore, replay: tuple[MazeId, ReplayId]) -> None:
    """Frames and their ordered ghost state load without loss."""
    _, replay_id = replay
    expected = frame()
    store.append(FrameBatch(replay_id, (expected,), ())).unwrap()
    assert store.frame(replay_id, Tick(0)).unwrap() == expected


def test_snapshot_applies_collectible_history(
    store: ReplayStore, replay: tuple[MazeId, ReplayId]
) -> None:
    """Snapshots apply every collectible change through the requested tick."""
    _, replay_id = replay
    first = frame(0)
    second = frame(1)
    changes = (
        CollectibleChange(Tick(0), TileIndex(0), Collectible.NONE),
        CollectibleChange(Tick(1), TileIndex(1), Collectible.POWER_PELLET),
    )
    store.append(FrameBatch(replay_id, (first, second), changes)).unwrap()

    snapshot = store.snapshot(replay_id, Tick(1)).unwrap()
    assert snapshot.collectibles == b"\x58"
    assert snapshot.player == second.player
    assert snapshot.ghosts == second.ghosts


def test_missing_records_return_errors(store: ReplayStore) -> None:
    """Unknown identifiers and ticks stay inside the typed error boundary."""
    assert isinstance(store.maze(MazeId(999)), Err)
    assert isinstance(store.replay(ReplayId(999)), Err)
    assert isinstance(store.frame(ReplayId(999), Tick(0)), Err)
    assert isinstance(store.finish(ReplayId(999)), Err)
