"""Pygame-based renderer (empty stub).

Draws whichever screen the game is currently on: main menu, in-game
HUD, pause menu, game-over, and victory, per the subject's User
Interface section. Left fully unimplemented -- only the shape of the
renderer is here.
"""

import pygame as pg

from pacman.maze_loader import Maze, Wall

from ..game.state import GameState
from ..models import GhostMode, GhostName, Position, Screen

# Classic arcade palette. No image assets exist in this repo, so every
# entity is drawn with pg's primitives (circle/rect/line) using
# these colors rather than sprites.
BACKGROUND_COLOR = (0, 0, 0)
TITLE_COLOR = (255, 255, 0)
WALL_COLOR = (33, 33, 255)
TEXT_COLOR = (255, 255, 255)
MENU_HIGHLIGHT_COLOR = (255, 255, 0)
GAME_OVER_COLOR = (255, 0, 0)

PLAYER_COLOR = (255, 255, 0)
PACGUM_COLOR = (255, 255, 255)
SUPER_PACGUM_COLOR = (255, 255, 0)

GHOST_COLORS: dict[GhostName, tuple[int, int, int]] = {
    GhostName.BLINKY: (255, 0, 0),
    GhostName.PINKY: (255, 184, 222),
    GhostName.INKY: (0, 255, 255),
    GhostName.CLYDE: (255, 184, 82),
}
FRIGHTENED_GHOST_COLOR = (33, 33, 255)
EATEN_GHOST_COLOR = (200, 200, 200)

# Entity sizes as a fraction of one tile, so they scale with whatever
# tile size a level's maze ends up using.
PLAYER_RADIUS_RATIO = 0.4
GHOST_RADIUS_RATIO = 0.4
PACGUM_RADIUS_RATIO = 0.1
SUPER_PACGUM_RADIUS_RATIO = 0.25
WALL_THICKNESS_RATIO = 0.08


class Renderer:
    """Owns the pg window and dispatches drawing by screen."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.surface: pg.Surface | None = None
        self.base_y = self.height // 2

    def init_window(self) -> None:
        """Initialize pg and open the game window."""
        pg.init()
        self.surface = pg.display.set_mode((self.width, self.height))
        pg.display.set_caption("Pac-Man")

    def _calc_tile_size(self, maze: Maze, available_height: int) -> int:
        return min(self.width // maze.width, available_height // maze.height)

    def _tile_center(
        self, position: Position, tile_size: int, offset_x: int, offset_y: int
    ) -> tuple[int, int]:
        return (
            offset_x + position.x * tile_size + tile_size // 2,
            offset_y + position.y * tile_size + tile_size // 2,
        )

    def _tile_rect(self, x: int, y: int, tile_size: int, offset_x: int, offset_y: int) -> pg.Rect:
        return pg.Rect(offset_x + x * tile_size, offset_y + y * tile_size, tile_size, tile_size)

    def render(self, state: GameState) -> None:
        """Draw the current frame for `state.screen`."""
        assert self.surface is not None
        self.surface.fill(BACKGROUND_COLOR)
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
                self.draw_game(state)
                self.draw_pause_menu(state)
            case Screen.GAME_OVER:
                self.draw_game_over(state)
            case Screen.VICTORY:
                self.draw_victory(state)
            case Screen.ERROR:
                self.draw_error(state)
        pg.display.flip()

    def draw_main_menu(self, state: GameState) -> None:
        """Draw: Start Game / View Highscores / Instructions / Exit."""
        assert self.surface is not None
        title_font = pg.font.Font(None, 72)
        title_surface = title_font.render("PAC-MAN", True, TITLE_COLOR)
        title_rect = title_surface.get_rect(center=(self.width // 2, self.height // 4))
        self.surface.blit(title_surface, title_rect)
        font = pg.font.Font(None, 36)
        options = ["Start Game", "View Highscore", "Instructions", "Exit"]
        for index, text in enumerate(options):
            color = MENU_HIGHLIGHT_COLOR if index == state.menu_selection else TEXT_COLOR
            text_surface = font.render(text, True, color)
            line_spacing = 50
            y = self.base_y + index * line_spacing
            rect = text_surface.get_rect(center=(self.width // 2, y))
            self.surface.blit(text_surface, rect)

    def draw_instructions(self) -> None:
        """Draw the controls and rules screen."""
        assert self.surface is not None
        lines = [
            "Arrow keys: Move Pac-Man",
            "P: Pause",
            "Esc: Back to Main Menu",
            "",
            "Eat all pacgums to clear the level",
            "Super pacgums make ghosts vulnerable - eat them for bonus points",
            "Avoid ghosts while they're chasing you",
            "Clear the level before time runs out!",
        ]
        font = pg.font.Font(None, 36)
        for index, text in enumerate(lines):
            text_surface = font.render(text, True, TEXT_COLOR)
            line_spacing = 33
            y = self.height // 4 + index * line_spacing
            rect = text_surface.get_rect(center=(self.width // 2, y))
            self.surface.blit(text_surface, rect)

    def draw_highscores(self, state: GameState) -> None:
        """Draw the top-10 highscore list."""
        assert self.surface is not None
        header_font = pg.font.Font(None, 75)
        header_surface = header_font.render("HIGHSCORES", True, TITLE_COLOR)
        header_rect = header_surface.get_rect(center=(self.width // 2, self.height // 6))
        self.surface.blit(header_surface, header_rect)
        lines = state.highscores
        sorted_scores = sorted(lines, key=lambda entry: entry.score, reverse=True)
        font = pg.font.Font(None, 45)
        surfaces = [
            font.render(f"{index + 1}. {entry.name}: {entry.score}", True, TEXT_COLOR)
            for index, entry in enumerate(sorted_scores[:10])
        ]
        max_width = max(s.get_width() for s in surfaces)
        x = (self.width - max_width) // 2
        line_spacing = 30
        for index, text_surface in enumerate(surfaces):
            y = self.height // 4 + index * line_spacing
            rect = text_surface.get_rect(topleft=(x, y))
            self.surface.blit(text_surface, rect)

    def draw_game(self, state: GameState) -> None:
        """Draw the maze, entities, and the HUD (score, lives, level,
        remaining time)."""
        assert self.surface is not None
        maze = state.board.maze
        hud_height = 40
        tile_size = self._calc_tile_size(maze, self.height - hud_height)
        offset_x = (self.width - tile_size * maze.width) // 2
        offset_y = hud_height + (self.height - hud_height - tile_size * maze.height) // 2
        for y in range(maze.height):
            for x in range(maze.width):
                cell = maze.cells[y][x]
                rect = self._tile_rect(x, y, tile_size, offset_x, offset_y)
                thickness = max(1, int(tile_size * WALL_THICKNESS_RATIO))
                if cell & Wall.NORTH:
                    pg.draw.line(self.surface, WALL_COLOR, rect.topleft, rect.topright, thickness)
                if cell & Wall.SOUTH:
                    pg.draw.line(
                        self.surface, WALL_COLOR, rect.bottomleft, rect.bottomright, thickness
                    )
                if cell & Wall.WEST:
                    pg.draw.line(self.surface, WALL_COLOR, rect.topleft, rect.bottomleft, thickness)
                if cell & Wall.EAST:
                    pg.draw.line(
                        self.surface, WALL_COLOR, rect.topright, rect.bottomright, thickness
                    )
        for position in state.board.pacgums:
            center = self._tile_center(position, tile_size, offset_x, offset_y)
            radius = int(tile_size * PACGUM_RADIUS_RATIO)
            pg.draw.circle(self.surface, PACGUM_COLOR, center, radius)
        for position in state.board.super_pacgums:
            center = self._tile_center(position, tile_size, offset_x, offset_y)
            radius = int(tile_size * SUPER_PACGUM_RADIUS_RATIO)
            pg.draw.circle(self.surface, SUPER_PACGUM_COLOR, center, radius)
        player_center = self._tile_center(state.player.position, tile_size, offset_x, offset_y)
        player_radius = int(tile_size * PLAYER_RADIUS_RATIO)
        pg.draw.circle(self.surface, PLAYER_COLOR, player_center, player_radius)
        for ghost in state.ghosts:
            center = self._tile_center(ghost.position, tile_size, offset_x, offset_y)
            radius = int(tile_size * GHOST_RADIUS_RATIO)
            match ghost.mode:
                case GhostMode.EATEN:
                    color = EATEN_GHOST_COLOR
                case GhostMode.FRIGHTENED:
                    color = FRIGHTENED_GHOST_COLOR
                case GhostMode.CHASING:
                    color = GHOST_COLORS[ghost.name]
            pg.draw.circle(self.surface, color, center, radius)
        lines = [
            f"Score: {state.player.score}",
            f"Level: {state.level_idx + 1}",
            f"Lives: {state.player.lives}",
            f"Time: {int(state.remaining_time)}",
        ]
        margin = 10
        gap = 80
        font = pg.font.Font(None, 30)
        surfaces = [font.render(text, True, TEXT_COLOR) for text in lines]
        total_width = sum(s.get_width() for s in surfaces) + gap * (len(surfaces) - 1)
        x = (self.width - total_width) // 2
        for text_surface in surfaces:
            rect = text_surface.get_rect(topleft=(x, margin))
            self.surface.blit(text_surface, rect)
            x += rect.width + gap

    def draw_pause_menu(self, state: GameState) -> None:
        """Draw: Resume / Return to main menu."""
        assert self.surface is not None
        title_font = pg.font.Font(None, 100)
        title_surface = title_font.render("PAUSED", True, TITLE_COLOR)
        title_rect = title_surface.get_rect(center=(self.width // 2, self.height // 4))
        self.surface.blit(title_surface, title_rect)
        options = ["Resume", "Main Menu"]
        font = pg.font.Font(None, 60)
        for index, text in enumerate(options):
            color = MENU_HIGHLIGHT_COLOR if index == state.menu_selection else TEXT_COLOR
            text_surface = font.render(text, True, color)
            line_spacing = 50
            y = self.base_y + index * line_spacing
            rect = text_surface.get_rect(center=(self.width // 2, y))
            self.surface.blit(text_surface, rect)

    def draw_game_over(self, state: GameState) -> None:
        """Draw the final score and the name-entry prompt for the
        highscore list."""
        assert self.surface is not None
        title_font = pg.font.Font(None, 150)
        title_surface = title_font.render("GAME OVER", 1, GAME_OVER_COLOR)
        title_rect = title_surface.get_rect(center=(self.width // 2, self.height // 3))
        self.surface.blit(title_surface, title_rect)
        score_surface = pg.font.Font(None, 70).render(f"Score: {state.player.score}", 1, TEXT_COLOR)
        score_rect = score_surface.get_rect(center=(self.width // 2, title_rect.bottom + 40))
        self.surface.blit(score_surface, score_rect)
        entry_surface = pg.font.Font(None, 40).render(
            f"Enter your name: {state.name_entry}", 1, TEXT_COLOR
        )
        entry_rect = entry_surface.get_rect(center=(self.width // 2, score_rect.bottom + 50))
        self.surface.blit(entry_surface, entry_rect)

    def draw_victory(self, state: GameState) -> None:
        """Draw the final score, a congratulatory message, and the
        name-entry prompt for the highscore list."""
        assert self.surface is not None
        title_surface = pg.font.Font(None, 150).render("YOU WON!!!", 1, "green")
        title_rect = title_surface.get_rect(center=(self.width // 2, self.height // 3))
        self.surface.blit(title_surface, title_rect)
        score_surface = pg.font.Font(None, 70).render(f"Score: {state.player.score}", 1, TEXT_COLOR)
        score_rect = score_surface.get_rect(center=(self.width // 2, title_rect.bottom + 40))
        self.surface.blit(score_surface, score_rect)
        entry_surface = pg.font.Font(None, 40).render(
            f"Enter your name: {state.name_entry}", 1, TEXT_COLOR
        )
        entry_rect = entry_surface.get_rect(center=(self.width // 2, score_rect.bottom + 50))
        self.surface.blit(entry_surface, entry_rect)

    def draw_error(self, state: GameState) -> None:
        """Draw: Error screen with Error message"""
        assert self.surface is not None
        font = pg.font.Font(None, 36)
        text_surface = font.render(state.error_msg, True, TEXT_COLOR)
        text_rect = text_surface.get_rect(center=(self.width // 2, self.height // 2))
        self.surface.blit(text_surface, text_rect)

    def handle_input(self) -> list[pg.event.Event]:
        """Poll and return pending pg events for the game loop
        to interpret."""
        raise NotImplementedError

    def quit(self) -> None:
        """Tear down the pg window."""
        raise NotImplementedError
