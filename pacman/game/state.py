"""The top-level game state machine.

Owns the current screen, level, score, and lives, and ties together
the board, player, ghosts, config, and highscore store. Screen flow
per the subject: Main Menu > start game > Win or Lose > Enter name
for highscore > Back to Main Menu.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from pacman.config import Config
from pacman.game.board import Board
from pacman.game.ghosts import eat_ghost, set_frightened, update_ghost
from pacman.game.player import respawn
from pacman.maze_loader import Maze, load_maze
from pacman.models import (
    Direction,
    Ghost,
    GhostMode,
    GhostName,
    HighscoreEntry,
    Player,
    Position,
    Screen,
)


def _spawn_ghosts(maze: Maze) -> list[Ghost]:
    corners: dict[GhostName, Position] = {
        GhostName.BLINKY: Position(0, 0),
        GhostName.CLYDE: Position((maze.width - 1), 0),
        GhostName.INKY: Position(0, maze.height - 1),
        GhostName.PINKY: Position(maze.width - 1, maze.height - 1),
    }
    ghosts = []
    for name, home in corners.items():
        ghosts.append(
            Ghost(
                name=name,
                position=home,
                facing_direction=Direction.DOWN,
                mode=GhostMode.CHASING,
                home_pos=home,
                frightened_timer=0,
                eaten_timer=0,
            )
        )
    return ghosts


@dataclass
class GameState:
    """The full mutable state of a running game session."""

    screen: Screen
    config: Config
    level_idx: int
    board: Board
    player: Player
    ghosts: list[Ghost]
    remaining_time: float
    highscores: list[HighscoreEntry]
    name_entry: str

    def start_game(self) -> GameState:
        """Transition from the main menu into level 1."""
        raise NotImplementedError

    def pause(self) -> GameState:
        """Transition into the pause screen."""
        return replace(self, screen=Screen.PAUSED)

    def resume(self) -> GameState:
        """Transition back from the pause screen into gameplay."""
        return replace(self, screen=Screen.PLAYING)

    def advance_level(self) -> GameState:
        """Move to the next level after all pacgums are eaten, or to the
        victory screen if that was the last level."""
        next_idx = self.level_idx + 1
        if next_idx >= len(self.config.levels):
            return replace(self, screen=Screen.VICTORY)
        next_lvl = self.config.levels[next_idx]
        new_maze = load_maze(next_lvl.width, next_lvl.height, next_lvl.seed).unwrap()
        new_board = Board(maze=new_maze)
        ghosts = _spawn_ghosts(new_maze)
        return replace(
            self,
            board=new_board,
            player=replace(self.player, position=Position(*new_maze.entry)),
            ghosts=ghosts,
            level_idx=next_idx,
            remaining_time=next_lvl.time,
            screen=Screen.PLAYING,
        )

    def lose_life(self) -> GameState:
        """Handle the player being touched by a non-edible ghost:
        decrement lives and respawn, or transition to game over.
        """
        new_lives = self.player.lives - 1
        if new_lives == 0:
            return replace(self, player=replace(self.player, lives=0), screen=Screen.GAME_OVER)
        respawned = respawn(self.player, Position(*self.board.maze.entry))
        new_player = replace(respawned, lives=new_lives)
        return replace(self, player=new_player, ghosts=_spawn_ghosts(self.board.maze))

    def update(self, dt: float) -> GameState:
        """Advance the game by one tick: moves ghosts, checks pacgum and
        ghost collisions, and ticks down the level timer.
        """
        new_player = self.player

        # Pre-movement collision check: catches a ghost the player was
        # already standing on before anything moves this tick. Needed
        # because a FRIGHTENED ghost flees on its own movement step below,
        # so checking only after movement would let it dodge every time.
        working_ghosts = []
        for g in self.ghosts:
            if g.position == new_player.position:
                match g.mode:
                    case GhostMode.CHASING:
                        return replace(self, player=new_player).lose_life()
                    case GhostMode.FRIGHTENED:
                        working_ghosts.append(eat_ghost(g))
                        new_player = replace(
                            new_player, score=new_player.score + self.config.points_per_ghost
                        )
                        continue
            working_ghosts.append(g)

        new_ghosts = [update_ghost(g, new_player, self.board, dt) for g in working_ghosts]
        new_board = self.board
        eaten_board = new_board.eat_pacgum(new_player.position)
        if eaten_board is not None:
            new_board = eaten_board
            new_player = replace(new_player, score=new_player.score + self.config.points_per_pacgum)
        else:
            eaten_board = new_board.eat_super_pacgum(new_player.position)
            if eaten_board is not None:
                new_board = eaten_board
                new_player = replace(
                    new_player, score=new_player.score + self.config.points_per_super_pacgum
                )
                new_ghosts = [
                    g if g.mode is GhostMode.EATEN else set_frightened(g) for g in new_ghosts
                ]
        final_ghosts = []
        for g in new_ghosts:
            if g.position == new_player.position:
                match g.mode:
                    case GhostMode.CHASING:
                        ticked = replace(
                            self, board=new_board, player=new_player, ghosts=new_ghosts
                        )
                        return ticked.lose_life()
                    case GhostMode.FRIGHTENED:
                        final_ghosts.append(eat_ghost(g))
                        new_player = replace(
                            new_player, score=new_player.score + self.config.points_per_ghost
                        )
                        continue
            final_ghosts.append(g)
        new_ghosts = final_ghosts
        return replace(self, board=new_board, player=new_player, ghosts=new_ghosts)
