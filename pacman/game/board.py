"""The playable board: a generated maze plus its remaining pacgums."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

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
