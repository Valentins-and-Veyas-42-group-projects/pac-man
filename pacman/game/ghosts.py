"""Ghost movement and behavior.

Ghosts chase the player when not edible, flee when the player has
eaten a super-pacgum, and respawn to their home corner a few seconds
after being eaten. The exact chase heuristic (distance-based, random,
etc.) is left open by the subject.
"""

from .board import Board
from ..models import Ghost, Player


def update_ghost(
    ghost: Ghost, player: Player, board: Board, dt: float
) -> Ghost:
    """Advance a single ghost by one tick, based on its current mode.

    Args:
        ghost: The ghost to update.
        player: The current player state, used for chase/flee targeting.
        board: The board, used for wall/corridor checks.
        dt: Elapsed time in seconds since the last update.

    Returns:
        The updated `Ghost`.
    """
    raise NotImplementedError


def set_frightened(ghost: Ghost) -> Ghost:
    """Return the ghost switched into `FRIGHTENED` mode (after the
    player eats a super-pacgum)."""
    raise NotImplementedError


def eat_ghost(ghost: Ghost) -> Ghost:
    """Return the ghost switched into `EATEN` mode, to respawn at its
    home corner after a short delay."""
    raise NotImplementedError


def respawn_ghost(ghost: Ghost) -> Ghost:
    """Return the ghost restored to `CHASING` mode at its home
    corner."""
    raise NotImplementedError
