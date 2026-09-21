"""Interactive maze visualizer: a small game loop wiring state, renderer and input.

Run with ``uv run python -m pacman.visualizer``. Arrow keys / WASD steer Pac-Man,
R new maze, P next palette, SPACE toggle shortest path, ESC/Q quit.
"""

import argparse
import sys
from pathlib import Path

import pygame
from typed_errs import Err, Some

from ..game.state import GameState, new_game, steer, update
from ..maze_loader import Maze, load_maze
from .intents import NewMaze, Quit, Steer
from .renderer import Renderer

FPS = 60
MAX_DT = 0.1  # seconds; a stall (window drag, breakpoint) must not become one giant step


def _new_maze(width: int, height: int, seed: int) -> Maze:
    match load_maze(width, height, Some(seed)):
        case Err() as err:
            err.print_diagnostic()
            sys.exit(1)
        case result:
            return result.value


def run(width: int, height: int, seed: int, palette_file: Path | None) -> None:
    """Open the window and run the game loop until the user quits."""
    renderer = Renderer(900, 900, palette_file)
    renderer.init_window()
    clock = pygame.time.Clock()
    state: GameState = new_game(_new_maze(width, height, seed), seed)
    running = True

    while running:
        for intent in renderer.handle_input():
            match intent:
                case Quit():
                    running = False
                case Steer(direction):
                    steer(state, direction)
                case NewMaze():
                    seed += 1
                    state = new_game(_new_maze(width, height, seed), seed)

        dt = min(clock.tick(FPS) / 1000, MAX_DT)
        update(state, dt)
        renderer.render(state)

    renderer.quit()


def main() -> None:
    """Parse CLI options and start the visualizer."""
    parser = argparse.ArgumentParser(description="Visualize generated Pac-Man mazes.")
    parser.add_argument("--width", type=int, default=21)
    parser.add_argument("--height", type=int, default=21)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--palette", type=Path, help="JSON file overriding palette colors")
    args = parser.parse_args()
    run(args.width, args.height, args.seed, args.palette)
