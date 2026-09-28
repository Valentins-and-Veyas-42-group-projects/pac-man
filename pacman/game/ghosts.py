"""Ghost movement and behavior.

Ghosts chase the player when not edible, flee when the player has
eaten a super-pacgum, and respawn to their home corner a few seconds
after being eaten. The exact chase heuristic (distance-based, random,
etc.) is left open by the subject.
"""

from dataclasses import replace

from ..models import Ghost, GhostMode, Player
from .board import Board

FRIGHTENED_TICKS = 360
RESPAWN_TICKS = 90


def update_ghost(ghost: Ghost, player: Player, board: Board, dt: float) -> Ghost:
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
    return replace(ghost, mode=GhostMode.FRIGHTENED, frightened_timer=FRIGHTENED_TICKS)


def eat_ghost(ghost: Ghost) -> Ghost:
    """Return the ghost switched into `EATEN` mode, to respawn at its
    home corner after a short delay."""
    return replace(ghost, mode=GhostMode.EATEN, eaten_timer=RESPAWN_TICKS, frightened_timer=0)


def respawn_ghost(ghost: Ghost) -> Ghost:
    """Return the ghost restored to `CHASING` mode at its home
    corner."""
    return replace(ghost, position=ghost.home_pos, mode=GhostMode.CHASING, eaten_timer=0, frightened_timer=0)
