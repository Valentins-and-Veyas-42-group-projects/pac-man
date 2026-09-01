"""Adapter over the assigned A-Maze-ing package.

The subject forbids writing our own maze generator: at project start
we're assigned another group's `A-Maze-ing` package and must adapt to
its interface (not the other way around), with `PERFECT` forced to
`False` so corridors are Pac-Man-compatible (multiple valid paths).
Swap in the actual import once a package is assigned for peer review.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum, IntFlag, auto
from typing import cast

from mazegenerator import MazeGenerator
from python_crimes import match_, pipe
from typed_errs import (
    Diagnostic,
    Err,
    Nothing,
    Ok,
    Option,
    Result,
    Some,
)

Position = tuple[int, int]


class MazeError(Enum):
    """Enumerate failure modes when generating or adapting a maze."""

    GENERATION_FAILED = "generation_failed"
    INVALID_GRID = "invalid_grid"


def maze_err(
    error: MazeError,
    diagnostic: Option[Diagnostic],
    context_msg: str,
) -> Err[MazeError]:
    """Create a maze error with consistent diagnostic context.

    Args:
        error: Maze error category.
        diagnostic: Optional diagnostic information.
        context_msg: Short description of the failed operation.

    Returns:
        A maze-loader error.
    """
    return Err(
        error=error,
        diagnostic=diagnostic,
        namespace="maze_loader",
        context_msg=context_msg,
    )


def maze_diagnostic(value: object, help_msg: str) -> Some[Diagnostic]:
    """Build a readable diagnostic for a generator boundary failure.

    Returns:
        A present diagnostic ready to attach to an error.
    """
    rendered = str(value)
    return Some(
        Diagnostic(
            filename="maze-generator",
            line_num=1,
            line_text=rendered,
            col_start=0,
            col_end=max(1, len(rendered)),
            help_msg=Some(help_msg),
        )
    )


class Wall(IntFlag):
    """Wall bits used by the assigned maze representation."""

    NORTH = 1
    EAST = 2
    SOUTH = 4
    WEST = 8


class Solver(Enum):
    """Available maze path-finding strategies."""

    BFS = auto()
    DFS = auto()


@pipe
def wall_for_direction(direction: Position) -> Wall:
    """Convert a movement delta into its corresponding wall bit.

    Args:
        direction: Movement delta as ``(dx, dy)``.

    Returns:
        Corresponding wall bit, or ``Wall(0)`` for an invalid direction.
    """
    return cast(
        Wall,
        (
            match_(direction)
            .case((0, -1))
            .then(Wall.NORTH)
            .case((1, 0))
            .then(Wall.EAST)
            .case((0, 1))
            .then(Wall.SOUTH)
            .case((-1, 0))
            .then(Wall.WEST)
            .default.then(Wall(0))
            .value
        ),
    )


@dataclass
class Maze:
    """Internal maze representation used by the game."""

    cells: list[list[int]]
    entry: Position
    exit: Position

    @property
    def width(self) -> int:
        """Maze width in cells."""
        return len(self.cells[0])

    @property
    def height(self) -> int:
        """Maze height in cells."""
        return len(self.cells)

    def in_bounds(self, x: int, y: int) -> bool:
        """Return whether a position lies inside the maze.

        Args:
            x: Horizontal cell coordinate.
            y: Vertical cell coordinate.

        Returns:
            Whether the coordinate lies inside the maze.
        """
        return 0 <= x < self.width and 0 <= y < self.height

    def can_move(
        self,
        x: int,
        y: int,
        dx: int,
        dy: int,
    ) -> bool:
        """Return whether movement to an adjacent cell is possible.

        Args:
            x: Current horizontal coordinate.
            y: Current vertical coordinate.
            dx: Horizontal movement delta.
            dy: Vertical movement delta.

        Returns:
            Whether the requested movement crosses no wall.
        """
        nx = x + dx
        ny = y + dy

        if not self.in_bounds(x, y):
            return False

        if not self.in_bounds(nx, ny):
            return False

        wall = (dx, dy) @ wall_for_direction

        if not wall:
            return False

        return not bool(self.cells[y][x] & wall)

    def neighbors(self, x: int, y: int) -> list[Position]:
        """Return directly reachable neighbouring cells.

        Args:
            x: Horizontal coordinate.
            y: Vertical coordinate.

        Returns:
            Reachable adjacent positions.
        """
        result: list[Position] = []

        if self.can_move(x, y, 0, -1):
            result.append((x, y - 1))

        if self.can_move(x, y, 1, 0):
            result.append((x + 1, y))

        if self.can_move(x, y, 0, 1):
            result.append((x, y + 1))

        if self.can_move(x, y, -1, 0):
            result.append((x - 1, y))

        return result

    def path(
        self,
        start: Position,
        target: Position,
        solver: Solver = Solver.BFS,
    ) -> Option[list[Position]]:
        """Find a path using the selected solving strategy.

        Args:
            start: Starting maze position.
            target: Desired destination.
            solver: Search strategy to use.

        Returns:
            ``Some(path)`` when reachable, otherwise ``Nothing``.
        """
        if not self.in_bounds(*start):
            return Nothing()

        if not self.in_bounds(*target):
            return Nothing()

        if start == target:
            return Some([start])

        def use_bfs(_solver: Solver) -> Option[list[Position]]:
            return self._bfs(start, target)

        def use_dfs(_solver: Solver) -> Option[list[Position]]:
            return self._dfs(start, target)

        return cast(
            Option[list[Position]],
            (
                match_(solver)
                .case(Solver.BFS)
                .then(use_bfs)
                .case(Solver.DFS)
                .then(use_dfs)
                .default.then(Nothing())
                .value
            ),
        )

    def _bfs(
        self,
        start: Position,
        target: Position,
    ) -> Option[list[Position]]:
        """Find the shortest unweighted path using breadth-first search.

        Returns:
            The discovered path, or ``Nothing`` when no path exists.
        """
        frontier: deque[Position] = deque([start])
        previous: dict[Position, Position] = {}
        seen: set[Position] = {start}

        while frontier:
            current = frontier.popleft()

            for neighbor in self.neighbors(*current):
                if neighbor in seen:
                    continue

                seen.add(neighbor)
                previous[neighbor] = current

                if neighbor == target:
                    return Some(
                        self._reconstruct(
                            previous,
                            start,
                            target,
                        )
                    )

                frontier.append(neighbor)

        return Nothing()

    def _dfs(
        self,
        start: Position,
        target: Position,
    ) -> Option[list[Position]]:
        """Find a reachable path using depth-first search.

        Returns:
            A discovered path, or ``Nothing`` when no path exists.
        """
        frontier: list[Position] = [start]
        previous: dict[Position, Position] = {}
        seen: set[Position] = {start}

        while frontier:
            current = frontier.pop()

            for neighbor in self.neighbors(*current):
                if neighbor in seen:
                    continue

                seen.add(neighbor)
                previous[neighbor] = current

                if neighbor == target:
                    return Some(
                        self._reconstruct(
                            previous,
                            start,
                            target,
                        )
                    )

                frontier.append(neighbor)

        return Nothing()

    @staticmethod
    def _reconstruct(
        previous: dict[Position, Position],
        start: Position,
        target: Position,
    ) -> list[Position]:
        """Reconstruct a discovered path from target back to start.

        Returns:
            The path ordered from start through target.
        """
        path: list[Position] = [target]
        current = target

        while current != start:
            current = previous[current]
            path.append(current)

        path.reverse()
        return path


def load_maze(
    width: int,
    height: int,
    seed: Option[int],
) -> Result[Maze, MazeError]:
    """Generate and adapt a maze from the assigned package.

    Args:
        width: Requested maze width.
        height: Requested maze height.
        seed: Optional deterministic generation seed.

    Returns:
        Generated maze or a maze generation error.
    """
    if width <= 0 or height <= 0:
        return maze_err(
            MazeError.INVALID_GRID,
            maze_diagnostic(
                f"width={width}, height={height}",
                "Use positive maze dimensions.",
            ),
            "Invalid requested maze dimensions",
        )

    try:
        generator = MazeGenerator(
            size=(width, height),
            perfect=False,
            seed=seed.unwrap_or(0),
        )

        cells = generator.maze

        if not cells or not cells[0]:
            return maze_err(
                MazeError.INVALID_GRID,
                maze_diagnostic(cells, "The generator must return a non-empty grid."),
                "Maze generator returned an empty grid",
            )

        if len(cells) != height or any(len(row) != width for row in cells):
            return maze_err(
                MazeError.INVALID_GRID,
                maze_diagnostic(
                    f"expected={width}x{height}, rows={len(cells)}",
                    "The generated grid must match the requested dimensions.",
                ),
                "Maze generator returned the wrong grid dimensions",
            )

        for y, row in enumerate(cells):
            for x, cell in enumerate(row):
                if isinstance(cell, bool) or not 0 <= cell <= 15:
                    return maze_err(
                        MazeError.INVALID_GRID,
                        maze_diagnostic(
                            f"cells[{y}][{x}]={cell!r}",
                            "Each maze cell must be an integer wall mask from 0 through 15.",
                        ),
                        "Maze generator returned an invalid wall mask",
                    )

                if x + 1 < width and bool(cell & Wall.EAST) != bool(row[x + 1] & Wall.WEST):
                    return maze_err(
                        MazeError.INVALID_GRID,
                        maze_diagnostic(
                            f"cells[{y}][{x}] east != cells[{y}][{x + 1}] west",
                            "Adjacent cells must agree about their shared wall.",
                        ),
                        "Maze generator returned inconsistent walls",
                    )

                if y + 1 < height and bool(cell & Wall.SOUTH) != bool(cells[y + 1][x] & Wall.NORTH):
                    return maze_err(
                        MazeError.INVALID_GRID,
                        maze_diagnostic(
                            f"cells[{y}][{x}] south != cells[{y + 1}][{x}] north",
                            "Adjacent cells must agree about their shared wall.",
                        ),
                        "Maze generator returned inconsistent walls",
                    )

        entry = generator.maze_entry
        exit_ = generator.maze_exit
        if not _position_in_bounds(entry, width, height):
            return maze_err(
                MazeError.INVALID_GRID,
                maze_diagnostic(entry, "The maze entry must be inside the generated grid."),
                "Maze generator returned an invalid entry",
            )

        if not _position_in_bounds(exit_, width, height):
            return maze_err(
                MazeError.INVALID_GRID,
                maze_diagnostic(exit_, "The maze exit must be inside the generated grid."),
                "Maze generator returned an invalid exit",
            )

        maze = Maze(
            cells=[row.copy() for row in cells],
            entry=entry,
            exit=exit_,
        )
        if isinstance(maze.path(entry, exit_), Nothing):
            return maze_err(
                MazeError.INVALID_GRID,
                maze_diagnostic(
                    f"entry={entry}, exit={exit_}",
                    "The generator must provide a traversable path from entry to exit.",
                ),
                "Maze generator returned an unreachable exit",
            )

        return Ok(maze)

    except Exception as error:
        return maze_err(
            MazeError.GENERATION_FAILED,
            maze_diagnostic(
                f"{type(error).__name__}: {error}",
                "Check the assigned A-Maze-ing package and requested maze settings.",
            ),
            "Maze generation failed",
        )


def _position_in_bounds(
    position: object,
    width: int,
    height: int,
) -> bool:
    """Return whether an external position is a valid grid coordinate."""
    match position:
        case (int() as x, int() as y) if not isinstance(x, bool) and not isinstance(y, bool):
            return 0 <= x < width and 0 <= y < height
        case _:
            return False
