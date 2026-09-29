"""Core data types shared across the game, config, and highscore modules.

Game fields remain stubs until their corresponding logic is implemented.
"""

from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    """The four directions the player and ghosts can move in."""

    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


class Cardinals(Enum):
    """Cardinal directions encoded as bit positions for cell walls."""

    NORTH = 0
    EAST = 1
    SOUTH = 2
    WEST = 3


@dataclass(frozen=True)
class Position:
    """A tile coordinate within the maze grid."""

    x: int
    y: int


class GhostName(Enum):
    """The four ghosts, one per maze corner."""

    BLINKY = 0
    PINKY = 1
    INKY = 2
    CLYDE = 3


class GhostMode(Enum):
    """A ghost's current behavior state."""

    CHASING = 0
    FRIGHTENED = 1
    EATEN = 2


@dataclass
class Player:
    """The Pac-Man player entity."""

    position: Position
    score: int
    lives: int = 3


@dataclass
class Ghost:
    """A single ghost entity."""

    name: GhostName
    position: Position
    facing_direction: Direction
    mode: GhostMode
    home_pos: Position
    frightened_timer: int
    eaten_timer: int


class Screen(Enum):
    """Which UI screen is currently active."""

    MAIN_MENU = 0
    INSTRUCTIONS = 1
    HIGHSCORES = 2
    PLAYING = 3
    PAUSED = 4
    GAME_OVER = 5
    VICTORY = 6


@dataclass(frozen=True, slots=True)
class HighscoreEntry:
    """A single row in the persistent highscore table."""

    name: str
    score: int
