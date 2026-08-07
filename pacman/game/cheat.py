"""Cheat mode flags, for peer-review evaluation purposes."""

from dataclasses import dataclass


@dataclass
class CheatFlags:
    """Toggleable cheats: invincibility, level skip, ghost freeze,
    extra lives, increased speed, etc. (see subject VI.5)."""

    def skip_level(self) -> None:
        """Marker method for the "level skip" cheat; wired up by the
        game engine to immediately clear the current level."""
        raise NotImplementedError
