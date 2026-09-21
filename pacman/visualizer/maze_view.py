"""Antialiased maze rendering.

pygame's own primitives are aliased, so the maze is drawn at `SUPERSAMPLE`
times its final size and shrunk with `smoothscale`. That antialiases every
shape (thick walls, round joins, circles) with no per-primitive tricks.
"""

import pygame

from ..maze_loader import Maze, Position, Wall
from .layout import SUPERSAMPLE, wall_width
from .palette import Palette


def render_maze(
    maze: Maze,
    palette: Palette,
    cell: int,
    path: list[Position] | None = None,
    pellets: bool = True,
) -> pygame.Surface:
    """Return the maze as a `maze.width*cell` by `maze.height*cell` surface.

    Pass `pellets=False` when the caller draws the pellets itself.
    """
    ss = cell * SUPERSAMPLE
    wall_w = wall_width(cell)
    size = (maze.width * ss + wall_w, maze.height * ss + wall_w)
    big = pygame.Surface(size)
    big.fill(palette.floor)
    half = wall_w // 2

    def center(pos: Position) -> tuple[int, int]:
        return (pos[0] * ss + ss // 2 + half, pos[1] * ss + ss // 2 + half)

    for pos, color in ((maze.entry, palette.entry), (maze.exit, palette.exit)):
        pygame.draw.rect(big, _tint(color, palette.floor), (pos[0] * ss + half, pos[1] * ss + half, ss, ss))

    if path:
        points = [center(p) for p in path]
        pygame.draw.lines(big, palette.path, False, points, max(2, ss // 6))
        for point in points:
            pygame.draw.circle(big, palette.path, point, max(1, ss // 12))

    for y, row in enumerate(maze.cells):
        for x, walls in enumerate(row):
            if pellets:
                pygame.draw.circle(big, palette.pellet, center((x, y)), max(1, ss // 10))
            x0, y0 = x * ss + half, y * ss + half
            x1, y1 = x0 + ss, y0 + ss
            for flag, start, end in (
                (Wall.NORTH, (x0, y0), (x1, y0)),
                (Wall.EAST, (x1, y0), (x1, y1)),
                (Wall.SOUTH, (x0, y1), (x1, y1)),
                (Wall.WEST, (x0, y0), (x0, y1)),
            ):
                if walls & flag:
                    pygame.draw.line(big, palette.wall, start, end, wall_w)
                    pygame.draw.circle(big, palette.wall, start, half)
                    pygame.draw.circle(big, palette.wall, end, half)

    for pos, color in ((maze.entry, palette.entry), (maze.exit, palette.exit)):
        pygame.draw.circle(big, color, center(pos), ss // 4)

    final = (maze.width * cell + max(1, cell // 8), maze.height * cell + max(1, cell // 8))
    return pygame.transform.smoothscale(big, final)


def _tint(color: tuple[int, int, int], floor: tuple[int, int, int]) -> tuple[int, int, int]:
    """Blend `color` 25% over `floor` for a subtle cell highlight."""
    return (
        (color[0] + floor[0] * 3) // 4,
        (color[1] + floor[1] * 3) // 4,
        (color[2] + floor[2] * 3) // 4,
    )
