"""Core data types shared across the game, config, and highscore
modules."""

from dataclasses import dataclass
from enum import Enum, auto


class Direction(Enum):
    """The four directions the player and ghosts can move in."""

    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()


@dataclass(frozen=True)
class Position:
    """A tile coordinate within the maze grid."""

    x: int
    y: int


class GhostName(Enum):
    """The four ghosts, one per maze corner."""

    BLINKY = auto()
    PINKY = auto()
    INKY = auto()
    CLYDE = auto()


class GhostMode(Enum):
    """A ghost's current behavior state."""

    CHASING = auto()
    FRIGHTENED = auto()
    EATEN = auto()


@dataclass
class Player:
    """The Pac-Man player entity."""

    position: Position
    direction: Direction
    lives: int
    score: int = 0


@dataclass
class Ghost:
    """A single ghost entity."""

    name: GhostName
    position: Position
    home_corner: Position
    mode: GhostMode = GhostMode.CHASING


class Screen(Enum):
    """Which UI screen is currently active."""

    MAIN_MENU = auto()
    INSTRUCTIONS = auto()
    HIGHSCORES = auto()
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()
    VICTORY = auto()


@dataclass
class HighscoreEntry:
    """A single row in the persistent highscore table.

    name is max 10 characters, alphanumeric and spaces only; score is
    a non-negative integer, per the subject's highscore requirements.
    """

    name: str
    score: int
