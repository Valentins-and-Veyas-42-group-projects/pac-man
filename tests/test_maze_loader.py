"""Integration tests for the assigned maze generator adapter."""

from pacman.maze_loader import MazeError, load_maze
from typed_errs import Err, Nothing, Some


def test_vendored_generator_produces_a_traversable_braided_maze() -> None:
    """The real package produces a valid maze with a reachable exit."""
    result = load_maze(width=20, height=15, seed=Some(42))
    maze = result.unwrap()

    assert maze.width == 20
    assert maze.height == 15
    assert not isinstance(maze.path(maze.entry, maze.exit), Nothing)


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
