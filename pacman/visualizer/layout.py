"""Pure screen-layout math: no pygame, so it is unit-testable without a display.

Computed once per window size. Converts between *logical* pixels (see
`pacman.game.actor.TILE`) and screen pixels.
"""

from dataclasses import dataclass

from ..game.actor import TILE
from ..maze_loader import Position

SUPERSAMPLE = 4  # the maze/sprites are drawn this many times larger, then smoothscaled
MARGIN = 24
HUD_HEIGHT = 32


def wall_width(cell: int) -> int:
    """Wall thickness in supersampled pixels for a `cell`-pixel tile."""
    return max(2, cell * SUPERSAMPLE // 8)


@dataclass(frozen=True, slots=True)
class Layout:
    """Where the maze sits in the window."""

    cell: int  # screen pixels per tile
    origin: tuple[int, int]  # top-left of the rendered maze surface
    surface_size: tuple[int, int]  # size of the rendered maze surface
    hud_anchor: tuple[int, int]  # midbottom of the HUD line

    @classmethod
    def compute(cls, window: tuple[int, int], cols: int, rows: int) -> "Layout":
        """Fit a `cols` by `rows` maze into `window`, leaving room for the HUD."""
        sw, sh = window
        # `* 8 // (n * 8 + 1)` reserves the outer wall's extra cell/8 pixels.
        cell = max(
            4,
            min((sw - 2 * MARGIN) * 8 // (cols * 8 + 1), (sh - 2 * MARGIN - HUD_HEIGHT) * 8 // (rows * 8 + 1)),
        )
        pad = max(1, cell // 8)  # room for the outer wall's thickness
        size = (cols * cell + pad, rows * cell + pad)
        origin = (sw // 2 - size[0] // 2, (sh - HUD_HEIGHT) // 2 - size[1] // 2)
        return cls(cell, origin, size, (sw // 2, sh - 8))

    @property
    def _corner(self) -> tuple[float, float]:
        """Screen position of the top-left tile's corner (walls are centered on edges)."""
        inset = wall_width(self.cell) // 2 / SUPERSAMPLE
        return (self.origin[0] + inset, self.origin[1] + inset)

    def to_screen(self, lx: float, ly: float) -> tuple[int, int]:
        """Logical pixel position to screen pixels."""
        scale = self.cell / TILE
        cx, cy = self._corner
        return (round(cx + lx * scale), round(cy + ly * scale))

    def to_logical(self, sx: float, sy: float) -> tuple[float, float]:
        """Screen pixel position to logical pixels (inverse of `to_screen`)."""
        scale = self.cell / TILE
        cx, cy = self._corner
        return ((sx - cx) / scale, (sy - cy) / scale)

    def tile_at(self, sx: float, sy: float) -> Position:
        """The tile under a screen pixel."""
        lx, ly = self.to_logical(sx, sy)
        return (int(lx // TILE), int(ly // TILE))
