"""The playable board: a generated maze plus its remaining pacgums."""

from dataclasses import dataclass

from ..models import Direction, Position


@dataclass
class Board:
    """Wraps a generated `Maze` and tracks which pacgums remain."""

    def is_wall(self, position: Position, direction: Direction) -> bool:
        """Return whether there is a wall in `direction` from
        `position`."""
        raise NotImplementedError

    def eat_pacgum(self, position: Position) -> bool:
        """Remove the pacgum at `position` if present.

        Returns:
            True if a normal pacgum was eaten at this position.
        """
        raise NotImplementedError

    def eat_super_pacgum(self, position: Position) -> bool:
        """Remove the super-pacgum at `position` if present.

        Returns:
            True if a super-pacgum was eaten at this position.
        """
        raise NotImplementedError

    def is_cleared(self) -> bool:
        """Return whether all pacgums and super-pacgums are eaten."""
        raise NotImplementedError
