"""The playable board: a generated maze plus its remaining pacgums."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field, replace

from typed_errs import Option

from ..maze_loader import Maze
from ..models import Direction, Position


@dataclass
class Board:
    """Wraps a generated `Maze` and tracks which pacgums remain."""

    maze: Maze
    pacgums: frozenset[Position] = field(default_factory=frozenset)
    super_pacgums: frozenset[Position] = field(default_factory=frozenset)

    def is_wall(self, position: Position, direction: Direction) -> bool:
        """Return whether there is a wall in `direction` from
        `position`.
        """
        dx, dy = direction.value
        return not self.maze.can_move(position.x, position.y, dx, dy)

    def eat_pacgum(self, position: Position) -> Board | None:
        """Return a new `Board` with the pacgum at `position` removed.

        Returns:
            The updated `Board`, or `None` if there was no pacgum there.
        """
        if position not in self.pacgums:
            return None
        return replace(self, pacgums=self.pacgums - {position})

    def eat_super_pacgum(self, position: Position) -> Board | None:
        """Return a new `Board` with the super-pacgum at `position` removed.

        Returns:
            The updated `Board`, or `None` if there was no super-pacgum there.
        """
        if position not in self.super_pacgums:
            return None
        return replace(self, super_pacgums=self.super_pacgums - {position})

    def is_cleared(self) -> bool:
        """Return whether all pacgums and super-pacgums are eaten."""
        return not self.pacgums and not self.super_pacgums


def spawn_pacgums(
    maze: Maze,
    pacgum_count: int,
    super_pacgum_count: int,
    seed: Option[int],
) -> tuple[frozenset[Position], frozenset[Position]]:
    visited: set[tuple[int, int]] = {maze.entry}
    queue: deque[tuple[int, int]] = deque([maze.entry])
    while queue:
        current = queue.popleft()
        for neighbor in maze.neighbors(*current):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    reachable = visited - {maze.entry}
    corners = [
        (0, 0),
        (maze.width - 1, 0),
        (0, maze.height - 1),
        (maze.width - 1, maze.height - 1),
    ]
    super_tiles: list[tuple[int, int]] = []
    for cx, cy in corners[:super_pacgum_count]:
        closest = min(reachable, key=lambda tile: abs(tile[0] - cx) + abs(tile[1] - cy))
        reachable.remove(closest)
        super_tiles.append(closest)
    extra_supers = super_pacgum_count - len(super_tiles)
    rng = random.Random(seed.unwrap_or(0))
    chosen = rng.sample(list(reachable), pacgum_count + extra_supers)
    overflow_supers = chosen[:extra_supers]
    normal_tiles = chosen[extra_supers:]
    all_supers = super_tiles + overflow_supers
    return (
        frozenset(Position(*tile) for tile in normal_tiles),
        frozenset(Position(*tile) for tile in all_supers),
    )
