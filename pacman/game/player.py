"""Player movement and lifecycle."""

from dataclasses import replace

from ..models import Direction, Player, Position
from .board import Board


def move(player: Player, board: Board, direction: Direction) -> Player:
    """Return a new `Player` moved one tile in `direction`, if the move is not blocked by a wall.

    Args:
        player: The current player state.
        board: The board to check for walls against.
        direction: The direction the player wants to move in.

    Returns:
        The (possibly unchanged) resulting `Player`.
    """
    if board.is_wall(player.position, direction):
        return player
    dx, dy = direction.value
    newpos = Position(player.position.x + dx, player.position.y + dy)
    return replace(player, position=newpos)


def respawn(player: Player, center: Position) -> Player:
    """Return a new `Player` respawned at the maze center after
    losing a life."""
    raise NotImplementedError
