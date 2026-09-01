"""The playable board: a generated maze plus its remaining pacgums."""

from dataclasses import dataclass

from ..models import Cardinals, Direction, Position


@dataclass
class Board:
    """Wraps a generated `Maze` and tracks which pacgums remain."""

    def is_wall(
        self, position: Position, cardinal: Cardinals, grid: list[list[int]]
    ) -> bool:  # TODO: Supposed to be the maze grid!
        """Return whether there is a wall in `direction` from
        `position`."""
        x, y = position.x, position.y
        if grid[y][x] & (1 << cardinal.value) == 0:
            return True
        return False

    def is_inbounds(self, position: Position, width: int, height: int) -> bool:
        x, y = position.x, position.y
        return 0 <= x < width and 0 <= y < height

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
