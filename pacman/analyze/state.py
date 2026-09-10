"""Reconstruct immutable tactical state from replay frames."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Result

from pacman.analyze.distance_backend import distances
from pacman.analyze.models import MazeGraph
from pacman.analyze.topology import TileKind, classify_tile
from pacman.replay.models import (
    Direction,
    Frame,
    Ghost,
    GhostState,
    Maze,
    Position,
    Tick,
    TileIndex,
)


@dataclass(frozen=True, slots=True)
class GhostDistance:
    """Distance and lethality of one ghost relative to Pac-Man."""

    ghost: Ghost
    tile: TileIndex
    distance: int
    dangerous: bool


@dataclass(frozen=True, slots=True)
class AnalysisState:
    """Cheap tactical facts derived from one replay frame."""

    tick: Tick
    player_tile: TileIndex
    legal_actions: tuple[Direction, ...]
    tile_kind: TileKind
    ghost_distances: tuple[GhostDistance, ...]


class AnalysisStateError(Enum):
    """Failures encountered while reconstructing one replay frame."""

    INVALID_PLAYER_TILE = "invalid_player_tile"
    INVALID_GHOST_TILE = "invalid_ghost_tile"
    UNCLASSIFIED_PLAYER_TILE = "unclassified_player_tile"
    UNREACHABLE_GHOST = "unreachable_ghost"


def state_err(
    error: AnalysisStateError,
) -> Err[AnalysisStateError]:
    """Create an analysis-state error with consistent context.

    Returns:
        A contextual analysis-state error.
    """
    return Err(
        error=error,
        namespace="analysis_state",
        context_msg="Failed to reconstruct frame analysis state",
    )


def position_in_maze(
    maze: Maze,
    position: Position,
) -> bool:
    """Return whether a replay position is inside the maze."""
    x = int(position.x)
    y = int(position.y)

    return 0 <= x < maze.width and 0 <= y < maze.height


def analyze_frame(
    graph: MazeGraph,
    maze: Maze,
    frame: Frame,
) -> Result[AnalysisState, AnalysisStateError]:
    """Reconstruct cheap tactical facts for one replay frame.

    Args:
        graph: Immutable graph built from the replay maze.
        maze: Replay maze used for position conversion.
        frame: Replay frame being analyzed.

    Returns:
        Reconstructed tactical state or a typed validation error.
    """
    player_position = frame.player.position

    if not position_in_maze(maze, player_position):
        return state_err(AnalysisStateError.INVALID_PLAYER_TILE)

    player_tile = maze.tile_index(player_position)

    if not graph.contains(player_tile):
        return state_err(AnalysisStateError.INVALID_PLAYER_TILE)

    legal_actions = tuple(move.direction for move in graph.neighbors(player_tile))

    tile_kind = classify_tile(graph, player_tile)

    if isinstance(tile_kind, Nothing):
        return state_err(AnalysisStateError.UNCLASSIFIED_PLAYER_TILE)

    distance_field = distances(graph, player_tile)

    if isinstance(distance_field, Err):
        return state_err(AnalysisStateError.INVALID_PLAYER_TILE)

    ghost_distances: list[GhostDistance] = []

    for ghost in frame.ghosts:
        if not position_in_maze(maze, ghost.position):
            return state_err(AnalysisStateError.INVALID_GHOST_TILE)

        ghost_tile = maze.tile_index(ghost.position)

        if not graph.contains(ghost_tile):
            return state_err(AnalysisStateError.INVALID_GHOST_TILE)

        distance = distance_field.value[int(ghost_tile)]
        if distance < 0:
            return state_err(AnalysisStateError.UNREACHABLE_GHOST)

        dangerous = ghost.state not in (
            GhostState.FRIGHTENED,
            GhostState.EATEN,
        )

        ghost_distances.append(
            GhostDistance(
                ghost=ghost.ghost,
                tile=ghost_tile,
                distance=distance,
                dangerous=dangerous,
            )
        )

    return Ok(
        AnalysisState(
            tick=frame.tick,
            player_tile=player_tile,
            legal_actions=legal_actions,
            tile_kind=tile_kind.value,
            ghost_distances=tuple(ghost_distances),
        )
    )
