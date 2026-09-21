"""Color palettes for the maze visualizer.

Every color the visualizer draws comes from a `Palette`, so restyling is a
matter of editing one place: add an entry to `PALETTES` below, or pass a JSON
file with `--palette` (see `Palette.from_file`) that overrides any subset of
fields on top of a built-in palette.
"""

import json
from dataclasses import dataclass, fields, replace
from pathlib import Path

Color = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Palette:
    """Every color used by the visualizer. Defaults are the classic look."""

    background: Color = (0, 0, 0)
    floor: Color = (8, 8, 24)
    wall: Color = (33, 33, 222)
    pellet: Color = (255, 184, 174)
    pacman: Color = (255, 255, 0)
    entry: Color = (255, 255, 0)
    exit: Color = (255, 0, 0)
    path: Color = (0, 255, 255)
    text: Color = (222, 222, 222)

    @classmethod
    def from_file(cls, path: Path, base: "Palette | None" = None) -> "Palette":
        """Load a palette from JSON, overriding `base` (default: classic).

        The file maps field names to ``[r, g, b]`` lists or ``"#rrggbb"``
        strings. Unknown names and malformed colors raise `ValueError`.
        """
        raw = json.loads(path.read_text())
        known = {f.name for f in fields(cls)}
        if not isinstance(raw, dict) or not set(raw) <= known:
            raise ValueError(f"{path}: expected an object with keys from {sorted(known)}")
        return replace(base or cls(), **{k: _parse_color(v) for k, v in raw.items()})


def _parse_color(value: object) -> Color:
    if isinstance(value, str) and len(value) == 7 and value[0] == "#":
        return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
    if isinstance(value, list) and len(value) == 3 and all(isinstance(c, int) and 0 <= c <= 255 for c in value):
        return (value[0], value[1], value[2])
    raise ValueError(f"invalid color {value!r}: use [r, g, b] or '#rrggbb'")


# Press P in the visualizer to cycle through these, in order.
PALETTES: dict[str, Palette] = {
    "classic": Palette(),
    "sunset": Palette(
        background=(24, 12, 28),
        floor=(40, 20, 48),
        wall=(255, 121, 90),
        pellet=(255, 214, 150),
        pacman=(255, 230, 109),
        entry=(120, 255, 180),
        exit=(255, 80, 140),
        path=(255, 230, 109),
        text=(255, 220, 210),
    ),
    "mono": Palette(
        background=(250, 250, 250),
        floor=(240, 240, 240),
        wall=(30, 30, 30),
        pellet=(120, 120, 120),
        pacman=(30, 30, 30),
        entry=(60, 60, 60),
        exit=(0, 0, 0),
        path=(200, 60, 60),
        text=(40, 40, 40),
    ),
}
