"""Build immutable adjacency graphs from persisted maze topology."""

from typing import TypeAlias

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.replay.maze_codec import decode_topology
from pacman.replay.models import Direction, Maze, TileIndex

from .models import MazeGraph, MazeGraphError, Move

DirectionSpec: TypeAlias = tuple[Direction, int, int, int, int]

NORTH = 1
EAST = 2
SOUTH = 4
WEST = 8

DIRECTIONS: tuple[DirectionSpec, ...] = (
    (Direction.UP, 0, -1, NORTH, SOUTH),
    (Direction.RIGHT, 1, 0, EAST, WEST),
    (Direction.DOWN, 0, 1, SOUTH, NORTH),
    (Direction.LEFT, -1, 0, WEST, EAST),
)


def graph_err(error: MazeGraphError) -> Err[MazeGraphError]:
    """Create a maze graph error with consistent context.

    Args:
        error: Maze graph error category.

    Returns:
        A contextual maze graph error.
    """
    return Err(
        error=error,
        namespace="maze_graph",
        context_msg="Failed to construct maze graph",
    )


def tile_index(width: int, x: int, y: int) -> TileIndex:
    """Convert maze coordinates into a row-major tile index.

    Args:
        width: Maze width in tiles.
        x: Horizontal coordinate.
        y: Vertical coordinate.

    Returns:
        Corresponding replay tile index.
    """
    return TileIndex(y * width + x)


def wrapped_position(
    width: int,
    height: int,
    x: int,
    y: int,
    direction: Direction,
) -> Option[tuple[int, int]]:
    """Return the opposite boundary position for an outward move."""
    if direction is Direction.LEFT and x == 0 and width > 1:
        return Some((width - 1, y))
    if direction is Direction.RIGHT and x == width - 1 and width > 1:
        return Some((0, y))
    if direction is Direction.UP and y == 0 and height > 1:
        return Some((x, height - 1))
    if direction is Direction.DOWN and y == height - 1 and height > 1:
        return Some((x, 0))
    return Nothing()


def build_maze_graph(
    maze: Maze,
) -> Result[MazeGraph, MazeGraphError]:
    """Decode persisted topology into an immutable adjacency graph.

    Args:
        maze: Replay maze containing packed four-bit wall masks.

    Returns:
        A graph or a typed error for invalid topology.
    """
    decoded = decode_topology(
        maze.topology,
        maze.width,
        maze.height,
    )

    if isinstance(decoded, Err):
        return graph_err(MazeGraphError.INVALID_TOPOLOGY)

    cells = decoded.value
    moves_by_tile: list[tuple[Move, ...]] = []

    for y in range(maze.height):
        for x in range(maze.width):
            cell = cells[y][x]
            moves: list[Move] = []

            for direction, dx, dy, wall, opposite_wall in DIRECTIONS:
                nx = x + dx
                ny = y + dy

                if not (0 <= nx < maze.width and 0 <= ny < maze.height):
                    wrapped = wrapped_position(
                        maze.width,
                        maze.height,
                        x,
                        y,
                        direction,
                    )
                    if isinstance(wrapped, Nothing):
                        continue

                    nx, ny = wrapped.value
                    neighbor = cells[ny][nx]
                    current_is_open = not bool(cell & wall)
                    neighbor_is_open = not bool(neighbor & opposite_wall)

                    if current_is_open and neighbor_is_open:
                        moves.append(
                            Move(
                                destination=tile_index(maze.width, nx, ny),
                                direction=direction,
                                wraparound=True,
                            )
                        )
                    continue

                neighbor = cells[ny][nx]
                current_is_open = not bool(cell & wall)
                neighbor_is_open = not bool(neighbor & opposite_wall)

                if current_is_open != neighbor_is_open:
                    return graph_err(MazeGraphError.ASYMMETRIC_EDGE)

                if current_is_open:
                    moves.append(
                        Move(
                            destination=tile_index(
                                maze.width,
                                nx,
                                ny,
                            ),
                            direction=direction,
                        )
                    )

            moves_by_tile.append(tuple(moves))

    return Ok(
        MazeGraph(
            width=maze.width,
            height=maze.height,
            moves=tuple(moves_by_tile),
        )
    )
