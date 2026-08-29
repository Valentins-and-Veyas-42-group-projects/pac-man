"""Topology analysis for maze graphs."""

from enum import Enum

from typed_errs import Nothing, Option, Some

from pacman.analyze.models import MazeGraph
from pacman.replay.models import Direction, TileIndex


class TileKind(Enum):
    """Local movement shape of one connected maze tile."""

    DEAD_END = "dead_end"
    CORRIDOR = "corridor"
    CORNER = "corner"
    INTERSECTION = "intersection"


OPPOSITES: frozenset[frozenset[Direction]] = frozenset({
    frozenset((Direction.UP, Direction.DOWN)),
    frozenset((Direction.LEFT, Direction.RIGHT)),
})


def classify_tile(
    graph: MazeGraph,
    tile: TileIndex,
) -> Option[TileKind]:
    """Classify a maze tile by its local graph topology.

    Args:
        graph: Immutable maze adjacency graph.
        tile: Tile to classify.

    Returns:
        The tile kind, or ``Nothing`` when the tile is outside the graph.
    """
    if not graph.contains(tile):
        return Nothing()

    moves = graph.neighbors(tile)
    degree = len(moves)

    if degree == 0:
        return Nothing()

    if degree == 1:
        return Some(TileKind.DEAD_END)

    if degree >= 3:
        return Some(TileKind.INTERSECTION)

    directions = frozenset(move.direction for move in moves)

    if directions in OPPOSITES:
        return Some(TileKind.CORRIDOR)

    return Some(TileKind.CORNER)
