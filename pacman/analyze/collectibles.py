"""Reconstruct immutable collectible state at a replay tick."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.replay.maze_codec import decode_collectibles
from pacman.replay.models import Collectible, CollectibleChange, Maze, Tick, TileIndex


class CollectibleStateError(Enum):
    """Failures encountered while reconstructing collectibles."""

    INVALID_ENCODING = "invalid_encoding"
    INVALID_TILE = "invalid_tile"


@dataclass(frozen=True, slots=True)
class CollectibleField:
    """Immutable collectible values indexed by maze tile."""

    tiles: tuple[Collectible, ...]

    def at(self, tile: TileIndex) -> Option[Collectible]:
        """Return the collectible at a valid tile."""
        index = int(tile)
        if index < 0 or index >= len(self.tiles):
            return Nothing()
        return Some(self.tiles[index])


def collectible_state_err(error: CollectibleStateError) -> Err[CollectibleStateError]:
    """Create a collectible-state error with consistent context.

    Returns:
        A contextual collectible-state error.
    """
    return Err(
        error=error,
        namespace="collectibles",
        context_msg="Failed to reconstruct collectible state",
    )


def reconstruct_collectibles(
    maze: Maze,
    changes: tuple[CollectibleChange, ...],
    tick: Tick,
) -> Result[CollectibleField, CollectibleStateError]:
    """Apply replay changes through one tick to initial maze collectibles.

    Returns:
        The reconstructed field or a typed validation error.
    """
    decoded = decode_collectibles(
        maze.initial_collectibles,
        maze.width * maze.height,
    )
    if isinstance(decoded, Err):
        return collectible_state_err(CollectibleStateError.INVALID_ENCODING)

    tiles = list(decoded.value)
    for change in changes:
        if change.tick > tick:
            continue
        index = int(change.tile)
        if index < 0 or index >= len(tiles):
            return collectible_state_err(CollectibleStateError.INVALID_TILE)
        tiles[index] = change.collectible

    return Ok(CollectibleField(tuple(tiles)))
