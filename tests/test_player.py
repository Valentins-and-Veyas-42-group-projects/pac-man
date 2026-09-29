"""Tests for player movement and respawn against a real `Board`/`Maze`."""

from pacman.game.board import Board
from pacman.game.player import move, respawn
from pacman.maze_loader import Maze
from pacman.models import Direction, Player, Position

OPEN_3X3 = Maze(cells=((0, 0, 0), (0, 0, 0), (0, 0, 0)), entry=(0, 0), exit=(2, 2))


def test_move_steps_one_tile_in_each_open_direction() -> None:
    """From the center of an open maze, every direction is walkable."""
    board = Board(maze=OPEN_3X3)
    player = Player(position=Position(1, 1), score=0)

    expected = {
        Direction.UP: Position(1, 0),
        Direction.DOWN: Position(1, 2),
        Direction.LEFT: Position(0, 1),
        Direction.RIGHT: Position(2, 1),
    }
    for direction, want in expected.items():
        assert move(player, board, direction).position == want


def test_move_is_blocked_by_the_maze_boundary() -> None:
    """A move that would leave the grid leaves the player unchanged."""
    board = Board(maze=OPEN_3X3)
    player = Player(position=Position(0, 0), score=0)

    result = move(player, board, Direction.UP)

    assert result.position == player.position


def test_move_is_blocked_by_a_wall() -> None:
    """A set wall bit blocks movement even though the tile is in bounds."""
    blocked_east = 2  # Wall.EAST
    maze = Maze(
        cells=((0, 0, 0), (0, blocked_east, 0), (0, 0, 0)),
        entry=(0, 0),
        exit=(2, 2),
    )
    board = Board(maze=maze)
    player = Player(position=Position(1, 1), score=0)

    result = move(player, board, Direction.RIGHT)

    assert result.position == player.position


def test_move_does_not_mutate_the_input_player() -> None:
    """`move` returns a new `Player`; it never edits the one it was given."""
    board = Board(maze=OPEN_3X3)
    player = Player(position=Position(1, 1), score=7, lives=2)

    result = move(player, board, Direction.RIGHT)

    assert player.position == Position(1, 1)
    assert result is not player
    assert result.score == 7
    assert result.lives == 2


def test_respawn_moves_to_center_and_keeps_score_and_lives() -> None:
    """Respawning relocates the player without touching score/lives."""
    player = Player(position=Position(2, 2), score=42, lives=1)

    result = respawn(player, Position(1, 1))

    assert result.position == Position(1, 1)
    assert result.score == 42
    assert result.lives == 1
