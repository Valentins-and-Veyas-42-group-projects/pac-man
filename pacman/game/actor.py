"""Delta-time movement along the maze grid (no pygame; unit-testable).

An `Actor` stands on a `tile` and has travelled `progress` logical pixels
towards the neighbouring tile in `heading` (0 means exactly on a tile
center). Every tile is `TILE` logical pixels wide whatever the window size,
and speed is `SPEED` pixels per *second*, so movement is frame-rate
independent. Walls are only ever asked about through `Maze.can_move`.
"""

from dataclasses import dataclass

from ..maze_loader import Maze, Position
from ..models import Direction

TILE = 24
CENTER = TILE // 2
SPEED = 60.0  # logical pixels per second

OPPOSITE = {
    Direction.UP: Direction.DOWN,
    Direction.DOWN: Direction.UP,
    Direction.LEFT: Direction.RIGHT,
    Direction.RIGHT: Direction.LEFT,
}


@dataclass
class Actor:
    """Something that walks the maze at `SPEED` pixels per second."""

    tile: Position
    progress: float = 0.0  # pixels travelled from `tile`'s center towards `heading`
    heading: Direction | None = None  # where it is moving right now
    wanted: Direction | None = None  # buffered input, applied at the next legal moment
    facing: Direction = Direction.RIGHT  # last heading, for drawing
    travelled: float = 0.0  # total pixels moved, drives the mouth animation

    @property
    def aligned(self) -> bool:
        """Whether the actor's center sits exactly on a tile center."""
        return self.progress == 0.0

    @property
    def pixel(self) -> tuple[float, float]:
        """The actor's center in logical pixels."""
        x: float = self.tile[0] * TILE + CENTER
        y: float = self.tile[1] * TILE + CENTER
        if self.heading is not None:
            x += self.heading.value[0] * self.progress
            y += self.heading.value[1] * self.progress
        return (x, y)

    def update(self, maze: Maze, dt: float) -> list[Position]:
        """Advance by `dt` seconds.

        Returns:
            Every tile whose center was reached during this update, in order.
            A long frame may cross several, so callers must not just look at
            `tile` afterwards.
        """
        arrived: list[Position] = []
        budget = SPEED * dt
        while budget > 0:
            if self.aligned:
                self._choose(maze)
            elif self.heading is not None and self.wanted == OPPOSITE[self.heading]:
                self._reverse()  # between tiles, only a U-turn is possible
            if self.heading is None:
                break

            self.facing = self.heading
            to_go = TILE - self.progress
            if budget < to_go:
                self.progress += budget
                self.travelled += budget
                break
            budget -= to_go
            self.travelled += to_go
            self.tile = (self.tile[0] + self.heading.value[0], self.tile[1] + self.heading.value[1])
            self.progress = 0.0
            arrived.append(self.tile)
        return arrived

    def _choose(self, maze: Maze) -> None:
        """At a tile center: take the buffered turn if legal, else stop at a wall."""
        x, y = self.tile
        if self.wanted is not None and maze.can_move(x, y, *self.wanted.value):
            self.heading = self.wanted
        elif self.heading is not None and not maze.can_move(x, y, *self.heading.value):
            self.heading = None

    def _reverse(self) -> None:
        """Turn around mid-tile: same pixel, but measured from the other tile."""
        assert self.heading is not None
        dx, dy = self.heading.value
        self.tile = (self.tile[0] + dx, self.tile[1] + dy)
        self.heading = OPPOSITE[self.heading]
        self.progress = TILE - self.progress
