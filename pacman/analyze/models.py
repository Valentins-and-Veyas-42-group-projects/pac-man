"""Immutable models shared by replay analysis stages."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Option

from pacman.replay.models import Direction, TileIndex


class MazeGraphError(Enum):
    """Failures encountered while constructing a maze graph."""

    INVALID_TOPOLOGY = "invalid_topology"
    ASYMMETRIC_EDGE = "asymmetric_edge"


@dataclass(frozen=True, slots=True)
class Move:
    """One legal directed move between adjacent maze tiles."""

    destination: TileIndex
    direction: Direction
    wraparound: bool = False


@dataclass(frozen=True, slots=True)
class MazeGraph:
    """Immutable adjacency graph indexed by replay tile index."""

    width: int
    height: int
    moves: tuple[tuple[Move, ...], ...]

    def contains(self, tile: TileIndex) -> bool:
        """Return whether a tile belongs to the graph."""
        return 0 <= int(tile) < len(self.moves)

    def neighbors(self, tile: TileIndex) -> tuple[Move, ...]:
        """Return legal moves from a tile."""
        return self.moves[int(tile)]


class PathfindingError(Enum):
    """Failures encountered while searching a maze graph."""

    INVALID_ORIGIN = "invalid_origin"


@dataclass(frozen=True, slots=True)
class DistanceField:
    """Shortest known distance from one origin to every graph tile."""

    origin: TileIndex
    distances: tuple[int, ...]
    previous: tuple[Option[TileIndex], ...]


@dataclass(frozen=True, slots=True)
class Path:
    """Ordered tiles forming one shortest route through a maze graph."""

    tiles: tuple[TileIndex, ...]

    @property
    def distance(self) -> int:
        """Number of graph edges traversed by the path."""
        return len(self.tiles) - 1
