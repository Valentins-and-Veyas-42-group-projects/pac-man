"""Pygame-based renderer (empty stub).

Draws whichever screen the game is currently on: main menu, in-game
HUD, pause menu, game-over, and victory, per the subject's User
Interface section. Left fully unimplemented -- only the shape of the
renderer is here.
"""

import pygame

from ..game.state import GameState
from ..models import Screen


class Renderer:
    """Owns the pygame window and dispatches drawing by screen."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.surface: pygame.Surface | None = None

    def init_window(self) -> None:
        """Initialize pygame and open the game window."""
        raise NotImplementedError

    def render(self, state: GameState) -> None:
        """Draw the current frame for `state.screen`."""
        raise NotImplementedError

    def draw_main_menu(self, state: GameState) -> None:
        """Draw: Start Game / View Highscores / Instructions / Exit."""
        raise NotImplementedError

    def draw_instructions(self) -> None:
        """Draw the controls and rules screen."""
        raise NotImplementedError

    def draw_highscores(self, state: GameState) -> None:
        """Draw the top-10 highscore list."""
        raise NotImplementedError

    def draw_game(self, state: GameState) -> None:
        """Draw the maze, entities, and the HUD (score, lives, level,
        remaining time)."""
        raise NotImplementedError

    def draw_pause_menu(self) -> None:
        """Draw: Resume / Return to main menu."""
        raise NotImplementedError

    def draw_game_over(self, state: GameState) -> None:
        """Draw the final score and the name-entry prompt for the
        highscore list."""
        raise NotImplementedError

    def draw_victory(self, state: GameState) -> None:
        """Draw the final score, a congratulatory message, and the
        name-entry prompt for the highscore list."""
        raise NotImplementedError

    def handle_input(self) -> list[pygame.event.Event]:
        """Poll and return pending pygame events for the game loop
        to interpret."""
        raise NotImplementedError

    def quit(self) -> None:
        """Tear down the pygame window."""
        raise NotImplementedError
