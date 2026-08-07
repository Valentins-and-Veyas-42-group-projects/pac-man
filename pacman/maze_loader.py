"""Adapter over the assigned A-Maze-ing package.

The subject forbids writing our own maze generator: at project start
we're assigned another group's `A-Maze-ing` package and must adapt to
its interface (not the other way around), with `PERFECT` forced to
`False` so corridors are Pac-Man-compatible (multiple valid paths).

This stub assumes the shared `mazegen.MazeGenerator` shape used across
the org's A-Maze-ing implementations (`generate()`, `.grid`, 4-bit
wall-encoded cells). Swap the import below for whichever package is
actually assigned once known.
"""

from dataclasses import dataclass
from enum import Enum, auto

from .errors import Diagnostic, Err, Result
from .models import Position


class MazeError(Enum):
    """Enumerate failure modes when generating or adapting a maze."""

    GENERATOR_UNAVAILABLE = auto()
    GENERATION_FAILED = auto()


def MazeErr(
    error: MazeError, diagnostic: Diagnostic | None = None
) -> Err[MazeError]:
    """Helper to bake module defaults into every maze Err."""
    return Err(
        error=error,
        diagnostic=diagnostic,
        namespace="maze_loader",
        context_msg="Maze generation failed",
    )


# Wall bits, matching the assigned generator's 4-bit cell encoding.
NORTH = 0b0001
EAST = 0b0010
SOUTH = 0b0100
WEST = 0b1000


@dataclass
class Maze:
    """A generated maze, adapted from the assigned package's own grid
    representation into our own corridor/wall model."""

    width: int
    height: int
    grid: list[list[int]]
    pacgum_positions: set[Position]
    super_pacgum_positions: set[Position]
    ghost_corners: tuple[Position, Position, Position, Position]
    center: Position


def load_maze(
    width: int,
    height: int,
    seed: int | str | None = None,
) -> Result[Maze, MazeError]:
    """Generate a maze via the assigned A-Maze-ing package.

    Always calls the generator with `perfect=False`, per the subject.

    Args:
        width: Maze width in cells.
        height: Maze height in cells.
        seed: Optional seed for reproducible generation (level 1 uses
            a fixed seed; later levels are random).

    Returns:
        Ok(Maze) on success, Err(MazeError) if the assigned generator
        is unavailable or generation fails.
    """
    raise NotImplementedError
