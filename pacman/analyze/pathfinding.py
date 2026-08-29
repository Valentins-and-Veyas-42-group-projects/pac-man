"""Shortest-path algorithms for immutable maze graphs."""

from collections import deque

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.models import (
    DistanceField,
    MazeGraph,
    Path,
    PathfindingError,
)
from pacman.replay.models import TileIndex

UNREACHABLE = -1


def pathfinding_err(error: PathfindingError) -> Err[PathfindingError]:
    """Create a pathfinding error with consistent context.

    Args:
        error: Pathfinding error category.

    Returns:
        A contextual pathfinding error.
    """
    return Err(
        error=error,
        namespace="pathfinding",
        context_msg="Failed to search maze graph",
    )


def bfs(
    graph: MazeGraph,
    origin: TileIndex,
) -> Result[DistanceField, PathfindingError]:
    """Calculate shortest distances from an origin with breadth-first search.

    Args:
        graph: Immutable graph to search.
        origin: Tile from which distances are measured.

    Returns:
        A complete distance field or an invalid-origin error.
    """
    if not graph.contains(origin):
        return pathfinding_err(PathfindingError.INVALID_ORIGIN)

    distances = [UNREACHABLE] * len(graph.moves)
    distances[int(origin)] = 0
    queue: deque[TileIndex] = deque([origin])
    previous: list[TileIndex | None] = [None] * len(graph.moves)

    while queue:
        current = queue.popleft()
        current_distance = distances[int(current)]

        for move in graph.neighbors(current):
            neighbor = move.destination
            neighbor_index = int(neighbor)

            if distances[neighbor_index] != UNREACHABLE:
                continue

            distances[neighbor_index] = current_distance + 1
            previous[neighbor_index] = current
            queue.append(neighbor)

    return Ok(
        DistanceField(
            origin=origin, distances=tuple(distances), previous=tuple(previous)
        )
    )


def distance_to(
    field: DistanceField,
    destination: TileIndex,
) -> Option[int]:
    """Look up one reachable distance without exposing its sentinel.

    Args:
        field: Previously calculated BFS distance field.
        destination: Tile whose distance is requested.

    Returns:
        The shortest distance, or ``Nothing`` when invalid or unreachable.
    """
    index = int(destination)

    if index < 0 or index >= len(field.distances):
        return Nothing()

    distance = field.distances[index]
    if distance == UNREACHABLE:
        return Nothing()

    return Some(distance)


def shortest_path(
    field: DistanceField,
    destination: TileIndex,
) -> Option[Path]:
    """Reconstruct one shortest path from a BFS distance field.

    Args:
        field: Previously calculated BFS distance and predecessor data.
        destination: Tile at which the path should end.

    Returns:
        The reconstructed path, or ``Nothing`` when unreachable or invalid.
    """
    if isinstance(distance_to(field, destination), Nothing):
        return Nothing()

    reversed_tiles = [destination]
    current = destination

    while current != field.origin:
        previous = field.previous[int(current)]

        if previous is None:
            return Nothing()

        reversed_tiles.append(previous)
        current = previous

    reversed_tiles.reverse()
    return Some(Path(tuple(reversed_tiles)))
