# uv run python delete_me/visualizer_tests/main.py

"""Temporary manual visual check for the Renderer. Opens a real window
showing whatever screen is set below; close the window to exit.
"""

import pygame
from pacman.config import default_config
from pacman.game.board import Board, spawn_pacgums
from pacman.game.state import GameState, _spawn_ghosts
from pacman.maze_loader import load_maze
from pacman.models import HighscoreEntry, Player, Position, Screen
from pacman.visualizer.renderer import Renderer
from typed_errs import Some


def main() -> None:
    """Render one screen in a real window until the user closes it."""
    renderer = Renderer(width=840, height=840)
    renderer.init_window()

    highscores = [
        HighscoreEntry(name="AAA", score=100),
        HighscoreEntry(name="BBB", score=11200),
        HighscoreEntry(name="CCC", score=9800),
        HighscoreEntry(name="DDD", score=8600),
        HighscoreEntry(name="EEE", score=7400),
        HighscoreEntry(name="FFF", score=6100),
        HighscoreEntry(name="GGG", score=4900),
        HighscoreEntry(name="HHH", score=3200),
        HighscoreEntry(name="III", score=2100),
        HighscoreEntry(name="JJJ", score=900),
        HighscoreEntry(name="JJI", score=9000),
    ]
    config = default_config()
    maze = load_maze(25, 25, Some(42)).unwrap()
    pacgums, super_pacgums = spawn_pacgums(maze, config.pacgum, config.super_pacgum, Some(42))
    ghosts = _spawn_ghosts(maze)
    state = GameState(
        screen=Screen.HIGHSCORES,
        config=config,
        level_idx=0,
        board=Board(maze=maze, pacgums=pacgums, super_pacgums=super_pacgums),
        player=Player(position=Position(0, 0), score=0),
        ghosts=ghosts,
        remaining_time=0.0,
        highscores=highscores,
        name_entry="",
        error_msg="",
        menu_selection=0,
    )

    renderer.render(state)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

    renderer.quit()


if __name__ == "__main__":
    main()
