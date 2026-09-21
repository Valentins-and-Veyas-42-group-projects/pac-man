"""The top-level game state machine.

Owns the current screen, level, score, and lives, and ties together
the board, player, ghosts, config, and highscore store. Screen flow
per the subject: Main Menu > start game > Win or Lose > Enter name
for highscore > Back to Main Menu.
"""

from dataclasses import dataclass

from ..maze_loader import Maze, Position
from ..models import Direction, Screen
from .actor import Actor


@dataclass
class GameState:
    """The full mutable state of a running game session.

    Only functions in this module mutate it; the renderer just reads it.
    """

    screen: Screen
    maze: Maze
    pacman: Actor
    pellets: set[Position]
    seed: int


def new_game(maze: Maze, seed: int) -> GameState:
    """Return a fresh playing state with Pac-Man on the maze entry."""
    tiles = {(x, y) for y in range(maze.height) for x in range(maze.width)}
    return GameState(Screen.PLAYING, maze, Actor(maze.entry), tiles - {maze.entry}, seed)


def steer(state: GameState, direction: Direction) -> None:
    """Buffer a turn request; it applies at the next legal tile center."""
    state.pacman.wanted = direction


def start_game(state: GameState) -> GameState:
    """Transition from the main menu into level 1."""
    raise NotImplementedError


def pause(state: GameState) -> GameState:
    """Transition into the pause screen."""
    raise NotImplementedError


def resume(state: GameState) -> GameState:
    """Transition back from the pause screen into gameplay."""
    raise NotImplementedError


def advance_level(state: GameState) -> GameState:
    """Move to the next level after all pacgums are eaten, or to the
    victory screen if that was the last level."""
    raise NotImplementedError


def lose_life(state: GameState) -> GameState:
    """Handle the player being touched by a non-edible ghost:
    decrement lives and respawn, or transition to game over."""
    raise NotImplementedError


def update(state: GameState, dt: float) -> GameState:
    """Advance the game by `dt` seconds: moves Pac-Man and eats pellets.

    Ghosts, ghost collisions and the level timer are not implemented yet.
    """
    if state.screen is Screen.PLAYING:
        for tile in state.pacman.update(state.maze, dt):
            state.pellets.discard(tile)
    return state
