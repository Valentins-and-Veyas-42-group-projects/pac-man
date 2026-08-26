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
NO_MAZE_DIAGNOSTIC: Option[Diagnostic] = Nothing()


class MazeError(Enum):
    """Enumerate failure modes when generating or adapting a maze."""

    GENERATION_FAILED = "generation_failed"
    INVALID_GRID = "invalid_grid"


def maze_err(
    error: MazeError,
    diagnostic: Option[Diagnostic] = NO_MAZE_DIAGNOSTIC,
) -> Err[MazeError]:
    """Create a maze error with consistent diagnostic context.

    Args:
        error: Maze error category.
        diagnostic: Optional diagnostic information.

    Returns:
        A maze-loader error.
    """
    return Err(
        error=error,
        diagnostic=diagnostic,
        namespace="maze_loader",
        context_msg="Maze generation failed",
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
    try:
        generator = MazeGenerator(
            size=(width, height),
            perfect=False,
            seed=seed.unwrap_or(0),
        )

        cells = generator.maze

        if not cells or not cells[0]:
            return maze_err(MazeError.INVALID_GRID)

        if any(len(row) != len(cells[0]) for row in cells):
            return maze_err(MazeError.INVALID_GRID)

        return Ok(
            Maze(
                cells=cells,
                entry=generator.maze_entry,
                exit=generator.maze_exit,
            )
        )

    except Exception:
        return maze_err(MazeError.GENERATION_FAILED)
