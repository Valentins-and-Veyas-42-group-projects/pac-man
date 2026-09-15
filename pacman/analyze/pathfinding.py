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
    previous: list[Option[TileIndex]] = [Nothing() for _ in graph.moves]

    while queue:
        current = queue.popleft()
        current_distance = distances[int(current)]

        for move in graph.neighbors(current):
            neighbor = move.destination
            neighbor_index = int(neighbor)

            if distances[neighbor_index] != UNREACHABLE:
                continue

            distances[neighbor_index] = current_distance + 1
            previous[neighbor_index] = Some(current)
            queue.append(neighbor)

    return Ok(DistanceField(origin=origin, distances=tuple(distances), previous=tuple(previous)))


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
        if isinstance(previous, Nothing):
            return Nothing()

        reversed_tiles.append(previous.value)
        current = previous.value

    reversed_tiles.reverse()
    return Some(Path(tuple(reversed_tiles)))


def path_from_distances(
    graph: MazeGraph,
    origin: TileIndex,
    destination: TileIndex,
    distances: tuple[int, ...],
) -> Option[Path]:
    """Reconstruct a directed route from an accelerator distance field.

    Args:
        graph: Directed graph used to produce the distances.
        origin: First tile in the route.
        destination: Last tile in the route.
        distances: Shortest distances from ``origin``.

    Returns:
        A valid forward path, or ``Nothing`` for malformed or unreachable data.
    """
    if len(distances) != len(graph.moves):
        return Nothing()
    if not graph.contains(origin) or not graph.contains(destination):
        return Nothing()
    if distances[int(origin)] != 0:
        return Nothing()

    destination_distance = distances[int(destination)]
    if destination_distance < 0:
        return Nothing()

    incoming: list[list[TileIndex]] = [[] for _ in graph.moves]
    for source, moves in enumerate(graph.moves):
        for move in moves:
            if graph.contains(move.destination):
                incoming[int(move.destination)].append(TileIndex(source))

    for source, moves in enumerate(graph.moves):
        source_distance = distances[source]
        if source_distance < -1:
            return Nothing()
        for move in moves:
            if not graph.contains(move.destination):
                return Nothing()
            neighbor_distance = distances[int(move.destination)]
            if source_distance >= 0 and (
                neighbor_distance < 0 or neighbor_distance > source_distance + 1
            ):
                return Nothing()

    for tile, tile_distance in enumerate(distances):
        if tile == int(origin) or tile_distance < 0:
            continue
        if not any(distances[int(previous)] == tile_distance - 1 for previous in incoming[tile]):
            return Nothing()

    reversed_tiles = [destination]
    current = destination
    current_distance = destination_distance
    while current != origin:
        previous = next(
            (
                candidate
                for candidate in incoming[int(current)]
                if distances[int(candidate)] == current_distance - 1
            ),
            None,
        )
        if previous is None:
            return Nothing()
        reversed_tiles.append(previous)
        current = previous
        current_distance -= 1

    if current_distance != 0 or len(reversed_tiles) - 1 != destination_distance:
        return Nothing()

    reversed_tiles.reverse()
    return Some(Path(tuple(reversed_tiles)))
