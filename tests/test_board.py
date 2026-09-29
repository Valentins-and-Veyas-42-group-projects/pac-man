"""Tests for `Board`'s wall/bounds checks against a real `Maze`."""

from pacman.game.board import Board
from pacman.maze_loader import Maze
from pacman.models import Direction, Position

# Wall.EAST from maze_loader: bit value 2. Set on the center cell only.
CENTER_BLOCKED_EAST = 2


def test_is_wall_false_through_an_open_passage() -> None:
    """A fully open maze has no walls between in-bounds neighbours."""
    maze = Maze(cells=((0, 0, 0), (0, 0, 0), (0, 0, 0)), entry=(0, 0), exit=(2, 2))
    board = Board(maze=maze)

    assert board.is_wall(Position(1, 1), Direction.RIGHT) is False


def test_is_wall_true_when_the_cell_has_that_wall_bit_set() -> None:
    """A set wall bit on the current cell blocks that direction."""
    maze = Maze(
        cells=((0, 0, 0), (0, CENTER_BLOCKED_EAST, 0), (0, 0, 0)),
        entry=(0, 0),
        exit=(2, 2),
    )
    board = Board(maze=maze)

    assert board.is_wall(Position(1, 1), Direction.RIGHT) is True
    # Unrelated directions from the same cell stay open.
    assert board.is_wall(Position(1, 1), Direction.LEFT) is False


def test_is_wall_true_at_the_maze_boundary() -> None:
    """Moving off the grid counts as blocked regardless of wall bits."""
    maze = Maze(cells=((0, 0, 0), (0, 0, 0), (0, 0, 0)), entry=(0, 0), exit=(2, 2))
    board = Board(maze=maze)

    assert board.is_wall(Position(0, 0), Direction.UP) is True
    assert board.is_wall(Position(0, 0), Direction.LEFT) is True
