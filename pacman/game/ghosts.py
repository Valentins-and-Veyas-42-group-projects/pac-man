"""Ghost movement and behavior.

Ghosts chase the player when not edible, flee when the player has
eaten a super-pacgum, and respawn to their home corner a few seconds
after being eaten. The exact chase heuristic (distance-based, random,
etc.) is left open by the subject.
"""

from dataclasses import replace

from ..models import Direction, Ghost, GhostMode, Player, Position
from .board import Board

FRIGHTENED_TICKS = 360
RESPAWN_TICKS = 90
TICK_RATE = 60


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
    ticks = round(dt * 60)
    match ghost.mode:
        case GhostMode.CHASING:
            directions = _legal_directions(ghost, board)
            chosen = _best_direction(ghost, directions, player.position, True)
            dx, dy = chosen.value
            new_pos = Position(ghost.position.x + dx, ghost.position.y + dy)
            return replace(ghost, position=new_pos, mode=GhostMode.CHASING, facing_direction=chosen)
        case GhostMode.FRIGHTENED:
            new_timer = max(0, ghost.frightened_timer - ticks)
            if new_timer == 0:
                return replace(ghost, mode=GhostMode.CHASING, frightened_timer=0)
            else:
                directions = _legal_directions(ghost, board)
                chosen = _best_direction(ghost, directions, player.position, False)
                dx, dy = chosen.value
                new_pos = Position(ghost.position.x + dx, ghost.position.y + dy)
                return replace(
                    ghost,
                    mode=GhostMode.FRIGHTENED,
                    frightened_timer=new_timer,
                    position=new_pos,
                    facing_direction=chosen,
                )
        case GhostMode.EATEN:
            new_timer = max(0, ghost.eaten_timer - ticks)
            if new_timer == 0:
                return respawn_ghost(ghost)
            else:
                return replace(ghost, eaten_timer=new_timer)


def _legal_directions(ghost: Ghost, board: Board) -> list[Direction]:
    reverse_dict = {
        Direction.UP: Direction.DOWN,
        Direction.LEFT: Direction.RIGHT,
        Direction.DOWN: Direction.UP,
        Direction.RIGHT: Direction.LEFT,
    }
    valid = []
    for direction in Direction:
        if not board.is_wall(ghost.position, direction):
            valid.append(direction)
    reverse = reverse_dict[ghost.facing_direction]
    non_reverse = [d for d in valid if d != reverse]
    return non_reverse if non_reverse else valid


def _best_direction(
    ghost: Ghost, directions: list[Direction], target: Position, minimize: bool
) -> Direction:
    best: Direction | None = None
    for direction in directions:
        dx, dy = direction.value
        candidate = Position(ghost.position.x + dx, ghost.position.y + dy)
        distance = abs(candidate.x - target.x) + abs(candidate.y - target.y)
        if best is None:
            best = direction
            best_distance = distance
        elif (minimize and distance < best_distance) or (not minimize and distance > best_distance):
            best = direction
            best_distance = distance
    assert best is not None
    return best


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
    return replace(
        ghost, position=ghost.home_pos, mode=GhostMode.CHASING, eaten_timer=0, frightened_timer=0
    )
