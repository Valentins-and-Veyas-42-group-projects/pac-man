"""Shared replay test fixtures."""

from pathlib import Path

import pytest
from pacman.replay.models import EncodedMaze, MazeId, ReplayId
from pacman.replay.store import ReplayStore


@pytest.fixture
def store(tmp_path: Path) -> ReplayStore:
    """Return an initialized replay store backed by a temporary database."""
    replay_store = ReplayStore(tmp_path / "replay.sqlite3")
    replay_store.initialize_replay().unwrap()
    return replay_store


@pytest.fixture
def maze() -> EncodedMaze:
    """Return a small encoded maze suitable for persistence tests."""
    return EncodedMaze(
        width=2,
        height=2,
        entry=(0, 0),
        exit=(1, 1),
        topology=b"\x21\x43",
        initial_collectibles=b"\x56",
        checksum=b"replay-test-maze",
    )


@pytest.fixture
def replay(store: ReplayStore, maze: EncodedMaze) -> tuple[MazeId, ReplayId]:
    """Persist a maze and replay, returning both identifiers."""
    maze_id = store.create_maze(maze).unwrap()
    replay_id = store.create_replay(
        maze_id=maze_id,
        tick_hz=60,
        level=1,
        simulation_version=2,
        config_hash=b"config-hash",
        rng_seed=42,
    ).unwrap()
    return maze_id, replay_id
