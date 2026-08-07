"""The top-level game state machine.

Owns the current screen, level, score, and lives, and ties together
the board, player, ghosts, config, and highscore store. Screen flow
per the subject: Main Menu > start game > Win or Lose > Enter name
for highscore > Back to Main Menu.
"""

from dataclasses import dataclass


@dataclass
class GameState:
    """The full mutable state of a running game session."""


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
    """Advance the game by one tick: moves ghosts, checks pacgum and
    ghost collisions, and ticks down the level timer."""
    raise NotImplementedError
