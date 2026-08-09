"""Adapter over the assigned A-Maze-ing package.

The subject forbids writing our own maze generator: at project start
we're assigned another group's `A-Maze-ing` package and must adapt to
its interface (not the other way around), with `PERFECT` forced to
`False` so corridors are Pac-Man-compatible (multiple valid paths).
Swap in the actual import once a package is assigned for peer review.
"""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Diagnostic, Err, Result


class MazeError(Enum):
    """Enumerate failure modes when generating or adapting a maze."""


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


@dataclass
class Maze:
    """A generated maze, adapted from the assigned package's own grid
    representation into our own corridor/wall model."""


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
