"""Cheat mode flags, for peer-review evaluation purposes."""

from dataclasses import dataclass


@dataclass
class CheatFlags:
    """Toggleable cheats. All default to off."""

    invincible: bool = False
    ghosts_frozen: bool = False
    extra_lives: int = 0
    speed_multiplier: float = 1.0

    def skip_level(self) -> None:
        """Marker method for the "level skip" cheat; wired up by the
        game engine to immediately clear the current level."""
        raise NotImplementedError
