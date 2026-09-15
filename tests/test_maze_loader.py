"""Integration tests for the assigned maze generator adapter."""

import pytest
from pacman.analyze.distance_backend import DistanceBackendKind, _accelerated_backend
from pacman.analyze.models import MazeGraph
from pacman.maze_loader import Maze, MazeError, load_maze
from pacman.replay.models import TileIndex
from typed_errs import Err, Nothing, Option, Some


def test_vendored_generator_produces_a_traversable_braided_maze() -> None:
    """The real package produces a valid maze with a reachable exit."""
    result = load_maze(width=20, height=15, seed=Some(42))
    maze = result.unwrap()

    assert maze.width == 20
    assert maze.height == 15
    assert not isinstance(maze.path(maze.entry, maze.exit), Nothing)


def test_maze_paths_use_the_shared_distance_router(monkeypatch: pytest.MonkeyPatch) -> None:
    """Maze validation/path lookup must use the selected shared backend."""

    class RecordingBackend:
        calls = 0

        def distances(
            self,
            graph: MazeGraph,
            origin: TileIndex,
        ) -> Option[tuple[int, ...]]:
            assert graph.contains(origin)
            self.calls += 1
            return Some(tuple(range(len(graph.moves))))

    backend = RecordingBackend()
    monkeypatch.setattr(
        "pacman.analyze.distance_backend._accelerated_backend",
        lambda: (DistanceBackendKind.NATIVE, Some(backend)),
    )

    maze = Maze(cells=[[13, 5, 7]], entry=(0, 0), exit=(2, 0))
    path = maze.path(maze.entry, maze.exit).unwrap()

    assert path == [(0, 0), (1, 0), (2, 0)]
    assert backend.calls >= 1
    _accelerated_backend.cache_clear()


def test_seed_is_deterministic() -> None:
    """A fixed seed produces the same topology through the real package."""
    first = load_maze(width=20, height=15, seed=Some(42)).unwrap()
    second = load_maze(width=20, height=15, seed=Some(42)).unwrap()
    assert first == second


def test_invalid_dimensions_return_a_diagnostic() -> None:
    """Bad dimensions never escape as a generator exception."""
    result = load_maze(width=0, height=15, seed=Some(42))
    assert isinstance(result, Err)
    assert result.error == MazeError.INVALID_GRID
    assert isinstance(result.diagnostic, Some)
