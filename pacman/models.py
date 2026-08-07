"""Core data types shared across the game, config, and highscore
modules. Left as bare stubs -- fields/members to be added once the
corresponding logic is implemented."""

from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    """The four directions the player and ghosts can move in."""


@dataclass(frozen=True)
class Position:
    """A tile coordinate within the maze grid."""


class GhostName(Enum):
    """The four ghosts, one per maze corner."""


class GhostMode(Enum):
    """A ghost's current behavior state."""


@dataclass
class Player:
    """The Pac-Man player entity."""


@dataclass
class Ghost:
    """A single ghost entity."""


class Screen(Enum):
    """Which UI screen is currently active."""


@dataclass
class HighscoreEntry:
    """A single row in the persistent highscore table."""
