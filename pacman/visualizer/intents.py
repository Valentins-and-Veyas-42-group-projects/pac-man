"""Semantic controller intents returned by `Renderer.handle_input`.

The renderer translates raw pygame events into these, so the game loop never
sees pygame. Only the state machine turns intents into state changes.
"""

from dataclasses import dataclass

from ..models import Direction


@dataclass(frozen=True, slots=True)
class Quit:
    """The user asked to close the game."""


@dataclass(frozen=True, slots=True)
class NewMaze:
    """The user asked for a fresh maze."""


@dataclass(frozen=True, slots=True)
class Steer:
    """The user pressed a direction."""

    direction: Direction


Intent = Quit | NewMaze | Steer
