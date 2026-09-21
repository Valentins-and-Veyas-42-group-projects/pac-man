"""Pygame-based renderer.

Read-only over `GameState`: it draws what the state says and never mutates it.
Raw pygame events are translated into semantic intents (`intents.py`); the
state machine is what turns those into state changes. Presentation-only
options (palette, path overlay) live here, not in `GameState`.

Only the in-game screen (`draw_game`) is implemented so far; the menu screens
are still stubs. The renderer knows nothing about replay recording or
analysis.
"""

from pathlib import Path

import pygame
from typed_errs import Some

from ..game.actor import CENTER, TILE
from ..game.state import GameState
from ..models import Direction, Screen
from .intents import Intent, NewMaze, Quit, Steer
from .layout import Layout
from .maze_view import render_maze
from .palette import PALETTES, Palette
from .sprite import MOUTH_CYCLE, build_pacman, build_pellet

STEER_KEYS: dict[int, Direction] = {
    pygame.K_UP: Direction.UP,
    pygame.K_w: Direction.UP,
    pygame.K_DOWN: Direction.DOWN,
    pygame.K_s: Direction.DOWN,
    pygame.K_LEFT: Direction.LEFT,
    pygame.K_a: Direction.LEFT,
    pygame.K_RIGHT: Direction.RIGHT,
    pygame.K_d: Direction.RIGHT,
}
QUIT_KEYS = (pygame.K_ESCAPE, pygame.K_q)
MOUTH_STEP = 4.0  # logical pixels travelled per mouth-animation frame


class Renderer:
    """Owns the pygame window and dispatches drawing by screen."""

    def __init__(self, width: int, height: int, palette_file: Path | None = None) -> None:
        self.width = width
        self.height = height
        self.surface: pygame.Surface | None = None

        self._palettes = dict(PALETTES)
        if palette_file is not None:
            self._palettes[palette_file.stem] = Palette.from_file(palette_file, base=self._palettes["classic"])
        self._names = list(self._palettes)
        self._palette_index = len(self._names) - 1 if palette_file is not None else 0
        self._show_path = False

        # Caches, rebuilt only when `_stale` (resize / palette / path toggle / new maze).
        self._stale = True
        self._maze_ref: object = None
        self._font: pygame.font.Font | None = None
        self._layout = Layout.compute((width, height), 1, 1)
        self._view = pygame.Surface((0, 0))
        self._pacman: dict[Direction, list[pygame.Surface]] = {}
        self._pellet = pygame.Surface((0, 0))
        self._pellet_px: dict[tuple[int, int], tuple[int, int]] = {}
        self._hud: tuple[str, pygame.Surface] | None = None

    @property
    def palette(self) -> Palette:
        """The palette currently in use."""
        return self._palettes[self._names[self._palette_index]]

    def init_window(self) -> None:
        """Initialize pygame and open the game window."""
        pygame.init()
        pygame.display.set_caption("pac-man")
        self.surface = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        self._font = pygame.font.Font(None, 24)

    def render(self, state: GameState) -> None:
        """Draw the current frame for `state.screen`."""
        match state.screen:
            case Screen.MAIN_MENU:
                self.draw_main_menu(state)
            case Screen.INSTRUCTIONS:
                self.draw_instructions()
            case Screen.HIGHSCORES:
                self.draw_highscores(state)
            case Screen.PLAYING:
                self.draw_game(state)
            case Screen.PAUSED:
                self.draw_pause_menu()
            case Screen.GAME_OVER:
                self.draw_game_over(state)
            case Screen.VICTORY:
                self.draw_victory(state)
        pygame.display.flip()

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
        """Draw the maze, pellets, Pac-Man, and a hint line."""
        screen = pygame.display.get_surface()
        assert screen is not None and self._font is not None, "call init_window() first"
        if self._stale or state.maze is not self._maze_ref:
            self._rebuild(screen.get_size(), state)

        palette = self.palette
        screen.fill(palette.background)
        screen.blit(self._view, self._layout.origin)

        screen.blits([(self._pellet, self._pellet_px[tile]) for tile in state.pellets], doreturn=False)

        pacman = state.pacman
        frames = self._pacman[pacman.facing]
        sprite = frames[int(pacman.travelled // MOUTH_STEP) % len(MOUTH_CYCLE)]
        px, py = self._layout.to_screen(*pacman.pixel)
        screen.blit(sprite, (px - sprite.get_width() // 2, py - sprite.get_height() // 2))

        hud = f"seed {state.seed}   palette {self._names[self._palette_index]}"
        hud += "   [arrows/WASD] move  [R] new  [P] palette  [SPACE] path  [Q] quit"
        if self._hud is None or self._hud[0] != hud:  # re-render text only when it changed
            self._hud = (hud, self._font.render(hud, True, palette.text))
        text = self._hud[1]
        anchor = self._layout.hud_anchor
        screen.blit(text, (anchor[0] - text.get_width() // 2, anchor[1] - text.get_height()))

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

    def handle_input(self) -> list[Intent]:
        """Poll pending pygame events and return them as semantic intents.

        Resizes and the purely visual keys (palette, path overlay) are handled
        here and never leave the renderer.
        """
        intents: list[Intent] = []
        for event in pygame.event.get():
            match event.type:
                case pygame.QUIT:
                    intents.append(Quit())
                case pygame.VIDEORESIZE:
                    self._stale = True
                case pygame.KEYDOWN if event.key in QUIT_KEYS:
                    intents.append(Quit())
                case pygame.KEYDOWN if event.key in STEER_KEYS:
                    intents.append(Steer(STEER_KEYS[event.key]))
                case pygame.KEYDOWN if event.key == pygame.K_r:
                    intents.append(NewMaze())
                case pygame.KEYDOWN if event.key == pygame.K_p:
                    self._palette_index = (self._palette_index + 1) % len(self._names)
                    self._stale = True
                case pygame.KEYDOWN if event.key == pygame.K_SPACE:
                    self._show_path = not self._show_path
                    self._stale = True
        return intents

    def quit(self) -> None:
        """Tear down the pygame window."""
        pygame.quit()

    def _rebuild(self, window: tuple[int, int], state: GameState) -> None:
        """Recompute layout and redo every expensive cached surface."""
        maze, palette = state.maze, self.palette
        self._layout = layout = Layout.compute(window, maze.width, maze.height)
        path = None
        if self._show_path and isinstance(found := maze.path(maze.entry, maze.exit), Some):
            path = found.value
        self._view = render_maze(maze, palette, layout.cell, path, pellets=False).convert()
        self._pacman = build_pacman(layout.cell, palette.pacman)
        self._pellet = build_pellet(layout.cell, palette.pellet)
        half_w, half_h = self._pellet.get_width() // 2, self._pellet.get_height() // 2
        self._pellet_px = {
            (x, y): (px - half_w, py - half_h)
            for y in range(maze.height)
            for x in range(maze.width)
            for px, py in [layout.to_screen(x * TILE + CENTER, y * TILE + CENTER)]
        }
        self._hud = None  # text color depends on the palette
        self._maze_ref = maze
        self._stale = False
