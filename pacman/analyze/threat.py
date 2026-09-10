"""Calculate earliest dangerous-ghost arrival times across a maze."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.distance_backend import distances
from pacman.analyze.models import MazeGraph
from pacman.analyze.state import GhostDistance
from pacman.replay.models import Ghost, TileIndex

NO_THREAT = -1


class ThreatError(Enum):
    """Failures encountered while constructing a threat field."""

    INVALID_GHOST_TILE = "invalid_ghost_tile"


def threat_err(
    error: ThreatError,
) -> Err[ThreatError]:
    """Create a threat-field error with consistent context.

    Returns:
        A contextual threat-field error.
    """
    return Err(
        error=error,
        namespace="threat",
        context_msg="Failed to calculate ghost threat field",
    )


@dataclass(frozen=True, slots=True)
class ThreatField:
    """Earliest dangerous-ghost arrival information for every tile."""

    etas: tuple[int, ...]
    ghosts: tuple[tuple[Ghost, ...], ...]

    def eta(self, tile: TileIndex) -> Option[int]:
        """Return the earliest dangerous-ghost arrival time."""
        index = int(tile)

        if index < 0 or index >= len(self.etas):
            return Nothing()

        eta = self.etas[index]

        if eta == NO_THREAT:
            return Nothing()

        return Some(eta)

    def owners(
        self,
        tile: TileIndex,
    ) -> tuple[Ghost, ...]:
        """Return ghosts tied for earliest arrival at a tile."""
        index = int(tile)

        if index < 0 or index >= len(self.ghosts):
            return ()

        return self.ghosts[index]


def build_threat_field(
    graph: MazeGraph,
    ghosts: tuple[GhostDistance, ...],
) -> Result[ThreatField, ThreatError]:
    """Calculate earliest dangerous-ghost arrivals across the graph.

    Args:
        graph: Immutable maze graph.
        ghosts: Ghost positions and lethality from reconstructed state.

    Returns:
        Combined threat field or a typed validation error.
    """
    etas = [NO_THREAT] * len(graph.moves)
    owners: list[list[Ghost]] = [[] for _ in graph.moves]

    for ghost in ghosts:
        if not ghost.dangerous:
            continue

        if not graph.contains(ghost.tile):
            return threat_err(ThreatError.INVALID_GHOST_TILE)

        distance_field = distances(graph, ghost.tile)

        if isinstance(distance_field, Err):
            return threat_err(ThreatError.INVALID_GHOST_TILE)

        for raw_tile, ghost_eta in enumerate(distance_field.value):
            if ghost_eta < 0:
                continue

            current_eta = etas[raw_tile]

            if current_eta == NO_THREAT or ghost_eta < current_eta:
                etas[raw_tile] = ghost_eta
                owners[raw_tile] = [ghost.ghost]
                continue

            if ghost_eta == current_eta:
                owners[raw_tile].append(ghost.ghost)

    return Ok(
        ThreatField(
            etas=tuple(etas),
            ghosts=tuple(tuple(tile_owners) for tile_owners in owners),
        )
    )
