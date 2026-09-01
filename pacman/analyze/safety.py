"""Compare Pac-Man and dangerous-ghost arrival times across a maze."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.models import DistanceField
from pacman.analyze.pathfinding import UNREACHABLE
from pacman.analyze.threat import NO_THREAT, ThreatField
from pacman.replay.models import TileIndex


class SafetyKind(Enum):
    """Tactical classification of one maze tile."""

    UNREACHABLE = "unreachable"
    UNTHREATENED = "unthreatened"
    SAFE = "safe"
    CONTESTED = "contested"
    DANGEROUS = "dangerous"


class SafetyError(Enum):
    """Failures encountered while combining arrival fields."""

    FIELD_SIZE_MISMATCH = "field_size_mismatch"


@dataclass(frozen=True, slots=True)
class TileSafety:
    """Pac-Man and ghost arrival comparison for one tile."""

    tile: TileIndex
    pacman_eta: Option[int]
    ghost_eta: Option[int]
    margin: Option[int]
    kind: SafetyKind


@dataclass(frozen=True, slots=True)
class SafetyField:
    """Immutable safety classification indexed by replay tile index."""

    tiles: tuple[TileSafety, ...]

    def at(self, tile: TileIndex) -> Option[TileSafety]:
        """Return safety information for a valid tile."""
        index = int(tile)
        if index < 0 or index >= len(self.tiles):
            return Nothing()
        return Some(self.tiles[index])


def safety_err(error: SafetyError) -> Err[SafetyError]:
    """Create a safety-field error with consistent context.

    Returns:
        A contextual safety-field error.
    """
    return Err(
        error=error,
        namespace="safety",
        context_msg="Failed to compare player and ghost arrival fields",
    )


def build_safety_field(
    player_distances: DistanceField,
    threats: ThreatField,
) -> Result[SafetyField, SafetyError]:
    """Compare Pac-Man ETA with earliest dangerous-ghost ETA per tile.

    Args:
        player_distances: BFS distances measured from Pac-Man's tile.
        threats: Earliest dangerous-ghost arrivals for the same graph.

    Returns:
        Immutable per-tile safety facts or a field-size error.
    """
    if len(player_distances.distances) != len(threats.etas) or len(threats.etas) != len(
        threats.ghosts
    ):
        return safety_err(SafetyError.FIELD_SIZE_MISMATCH)

    tiles: list[TileSafety] = []
    for raw_tile, pacman_eta in enumerate(player_distances.distances):
        ghost_eta = threats.etas[raw_tile]
        tile = TileIndex(raw_tile)

        if pacman_eta == UNREACHABLE:
            known_ghost_eta: Option[int] = Nothing() if ghost_eta == NO_THREAT else Some(ghost_eta)
            tiles.append(
                TileSafety(
                    tile,
                    Nothing(),
                    known_ghost_eta,
                    Nothing(),
                    SafetyKind.UNREACHABLE,
                )
            )
            continue

        if ghost_eta == NO_THREAT:
            tiles.append(
                TileSafety(
                    tile,
                    Some(pacman_eta),
                    Nothing(),
                    Nothing(),
                    SafetyKind.UNTHREATENED,
                )
            )
            continue

        margin = ghost_eta - pacman_eta
        if margin > 0:
            kind = SafetyKind.SAFE
        elif margin == 0:
            kind = SafetyKind.CONTESTED
        else:
            kind = SafetyKind.DANGEROUS

        tiles.append(
            TileSafety(
                tile,
                Some(pacman_eta),
                Some(ghost_eta),
                Some(margin),
                kind,
            )
        )

    return Ok(SafetyField(tuple(tiles)))
