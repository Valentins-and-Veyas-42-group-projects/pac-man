"""Player movement and lifecycle."""

from .board import Board
from ..models import Direction, Player, Position


def move(player: Player, board: Board, direction: Direction) -> Player:
    """Return a new `Player` moved one tile in `direction`, if the
    move is not blocked by a wall.

    Args:
        player: The current player state.
        board: The board to check for walls against.
        direction: The direction the player wants to move in.

    Returns:
        The (possibly unchanged) resulting `Player`.
    """
    raise NotImplementedError


def respawn(player: Player, center: Position) -> Player:
    """Return a new `Player` respawned at the maze center after
    losing a life."""
    raise NotImplementedError
