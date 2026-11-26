"""Ghost movement and behavior.

Ghosts chase the player when not edible, flee when the player has
eaten a super-pacgum, and respawn to their home corner a few seconds
after being eaten. The exact chase heuristic (distance-based, random,
etc.) is left open by the subject.
"""

import random
from collections import deque
from dataclasses import replace

from ..models import Direction, Ghost, GhostMode, GhostName, Player, Position
from .board import Board

FRIGHTENED_TICKS = 360
RESPAWN_TICKS = 90
TICK_RATE = 60
MOVE_INTERVAL_TICKS = 12
FRIGHTENED_MOVE_INTERVAL_TICKS = MOVE_INTERVAL_TICKS * 2
CLYDE_SHY_DISTANCE = 8
MAX_BFS_TILES = 300
GHOST_WANDER_RADIUS = 2


def update_ghost(
    ghost: Ghost, player: Player, board: Board, dt: float, all_ghosts: list[Ghost]
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
    ticks = round(dt * 60)
    blinky = next(g for g in all_ghosts if g.name is GhostName.BLINKY)
    match ghost.mode:
        case GhostMode.CHASING:
            new_move_timer = ghost.move_timer - ticks
            if new_move_timer > 0:
                return replace(ghost, move_timer=new_move_timer)
            directions = _legal_directions(ghost, board)
            if not directions:
                return replace(ghost, move_timer=0)
            if len(directions) == 1:
                chosen = directions[0]
            else:
                target = _target_for(ghost, player, blinky)
                retreating_to_corner = ghost.name is GhostName.CLYDE and target == ghost.home_pos
                bfs_direction, distance_to_target = _bfs_direction(ghost, target, board)
                if bfs_direction is None or (
                    retreating_to_corner and distance_to_target <= GHOST_WANDER_RADIUS
                ):
                    chosen = random.choice(directions)
                else:
                    chosen = bfs_direction
            dx, dy = chosen.value
            new_pos = Position(ghost.position.x + dx, ghost.position.y + dy)
            return replace(
                ghost,
                position=new_pos,
                mode=GhostMode.CHASING,
                facing_direction=chosen,
                move_timer=MOVE_INTERVAL_TICKS,
            )
        case GhostMode.FRIGHTENED:
            new_timer = max(0, ghost.frightened_timer - ticks)
            if new_timer == 0:
                return replace(ghost, mode=GhostMode.CHASING, frightened_timer=0)
            new_move_timer = ghost.move_timer - ticks
            if new_move_timer > 0:
                return replace(ghost, frightened_timer=new_timer, move_timer=new_move_timer)
            directions = _legal_directions(ghost, board)
            if not directions:
                return replace(ghost, frightened_timer=new_timer, move_timer=0)
            chosen = _best_direction(ghost, directions, player.position, False)
            dx, dy = chosen.value
            new_pos = Position(ghost.position.x + dx, ghost.position.y + dy)
            return replace(
                ghost,
                mode=GhostMode.FRIGHTENED,
                frightened_timer=new_timer,
                position=new_pos,
                facing_direction=chosen,
                move_timer=FRIGHTENED_MOVE_INTERVAL_TICKS,
            )
        case GhostMode.EATEN:
            new_timer = max(0, ghost.eaten_timer - ticks)
            if new_timer == 0:
                return respawn_ghost(ghost)
            else:
                return replace(ghost, eaten_timer=new_timer)


def _target_for(ghost: Ghost, player: Player, blinky: Ghost) -> Position:
    match ghost.name:
        case GhostName.BLINKY:
            return player.position
        case GhostName.PINKY:
            dx, dy = player.facing_direction.value
            return Position(player.position.x + dx * 4, player.position.y + dy * 4)
        case GhostName.INKY:
            dx, dy = player.facing_direction.value
            p2 = Position(player.position.x + dx * 2, player.position.y + dy * 2)
            return Position(2 * p2.x - blinky.position.x, 2 * p2.y - blinky.position.y)
        case GhostName.CLYDE:
            manhatten_distance = _manhattan_distance(ghost, player)
            if manhatten_distance > CLYDE_SHY_DISTANCE:
                return player.position
            return ghost.home_pos


def _bfs_direction(ghost: Ghost, target: Position, board: Board) -> tuple[Direction | None, int]:
    """Return the first step of the shortest path from the ghost toward
    `target`, plus the real distance (in moves, following corridors --
    not a straight line) to wherever that step leads toward.

    The direction is `None` when the ghost is already as close as it
    can get (distance `0`). Explores every tile the ghost can reach,
    so it can never get stuck orbiting a loop the way a greedy
    one-step heuristic can. If `target` itself isn't reachable (e.g. a
    projected target that lands outside the maze), steps toward
    whichever reachable tile is closest to it instead.
    """
    if ghost.position == target:
        return None, 0
    first_step: dict[Position, Direction | None] = {ghost.position: None}
    distance: dict[Position, int] = {ghost.position: 0}
    queue: deque[Position] = deque([ghost.position])
    while queue and len(first_step) < MAX_BFS_TILES:
        current = queue.popleft()
        for direction in Direction:
            if board.is_wall(current, direction):
                continue
            dx, dy = direction.value
            neighbor = Position(current.x + dx, current.y + dy)
            if neighbor not in first_step:
                step = first_step[current] or direction
                first_step[neighbor] = step
                distance[neighbor] = distance[current] + 1
                if neighbor == target:
                    return step, distance[neighbor]
                queue.append(neighbor)

    best_tile = min(first_step, key=lambda tile: abs(tile.x - target.x) + abs(tile.y - target.y))
    return first_step[best_tile], distance[best_tile]


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


def _manhattan_distance(ghost: Ghost, player: Player) -> int:
    return abs(ghost.position.x - player.position.x) + abs(ghost.position.y - player.position.y)


def _distance(ghost: Ghost, direction: Direction, target: Position) -> int:
    dx, dy = direction.value
    candidate = Position(ghost.position.x + dx, ghost.position.y + dy)
    return abs(candidate.x - target.x) + abs(candidate.y - target.y)


def _best_direction(
    ghost: Ghost, directions: list[Direction], target: Position, minimize: bool
) -> Direction:
    """Pick the direction with the smallest/largest distance to `target`.

    `directions` must be non-empty; ties keep the first candidate seen,
    which follows `Direction`'s declaration order (UP, DOWN, LEFT, RIGHT).
    """
    best = directions[0]
    best_distance = _distance(ghost, best, target)
    for direction in directions[1:]:
        distance = _distance(ghost, direction, target)
        if (minimize and distance < best_distance) or (not minimize and distance > best_distance):
            best = direction
            best_distance = distance
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
