"""The top-level game state machine.

Owns the current screen, level, score, and lives, and ties together
the board, player, ghosts, config, and highscore store. Screen flow
per the subject: Main Menu > start game > Win or Lose > Enter name
for highscore > Back to Main Menu.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from typed_errs import Err

from pacman.config import Config
from pacman.game.board import Board, spawn_pacgums
from pacman.game.ghosts import eat_ghost, set_frightened, update_ghost
from pacman.game.player import move, respawn
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

PLAYER_MOVE_INTERVAL_TICKS = 10


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
                move_timer=0,
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
    error_msg: str
    menu_selection: int

    def start_game(self) -> GameState:
        """Transition from the main menu into level 1."""
        level = self.config.levels[0]
        maze_result = load_maze(level.width, level.height, level.seed)
        if isinstance(maze_result, Err):
            return replace(
                self,
                screen=Screen.ERROR,
                error_msg=maze_result.context_msg or "Failed to generate the maze.",
            )
        new_maze = maze_result.value
        pacgums, super_pacgums = spawn_pacgums(
            new_maze, self.config.pacgum, self.config.super_pacgum, level.seed
        )
        new_board = Board(maze=new_maze, pacgums=pacgums, super_pacgums=super_pacgums)
        ghosts = _spawn_ghosts(new_maze)
        return replace(
            self,
            board=new_board,
            player=replace(
                self.player, position=Position(*new_maze.center), score=0, lives=self.config.lives
            ),
            ghosts=ghosts,
            level_idx=0,
            remaining_time=level.time,
            screen=Screen.PLAYING,
            name_entry="",
            error_msg="",
        )

    @staticmethod
    def new(config: Config, highscores: list[HighscoreEntry]) -> GameState:
        level = config.levels[0]
        maze_result = load_maze(level.width, level.height, level.seed)
        if isinstance(maze_result, Err):
            return GameState(
                screen=Screen.ERROR,
                error_msg=maze_result.context_msg or "Failed to generate Maze",
                board=Board(maze=Maze(cells=((0,),), entry=(0, 0), exit=(0, 0))),
                ghosts=[],
                config=config,
                level_idx=0,
                player=Player(position=Position(0, 0), score=0),
                highscores=highscores,
                name_entry="",
                menu_selection=0,
                remaining_time=0.0,
            )
        new_maze = maze_result.value
        pacgums, super_pacgums = spawn_pacgums(
            new_maze, config.pacgum, config.super_pacgum, level.seed
        )
        new_board = Board(maze=new_maze, pacgums=pacgums, super_pacgums=super_pacgums)
        ghosts = _spawn_ghosts(new_maze)
        return GameState(
            screen=Screen.MAIN_MENU,
            config=config,
            highscores=highscores,
            board=new_board,
            player=Player(position=Position(*new_maze.entry), score=0, lives=config.lives),
            ghosts=ghosts,
            level_idx=0,
            remaining_time=0.0,
            name_entry="",
            error_msg="",
            menu_selection=0,
        )

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
            return replace(self, screen=Screen.VICTORY, error_msg="")
        next_lvl = self.config.levels[next_idx]
        maze_result = load_maze(next_lvl.width, next_lvl.height, next_lvl.seed)
        if isinstance(maze_result, Err):
            return replace(
                self,
                screen=Screen.ERROR,
                error_msg=maze_result.context_msg or "Failed to generate the maze.",
            )
        new_maze = maze_result.value
        pacgums, super_pacgums = spawn_pacgums(
            new_maze, self.config.pacgum, self.config.super_pacgum, next_lvl.seed
        )
        new_board = Board(maze=new_maze, pacgums=pacgums, super_pacgums=super_pacgums)
        ghosts = _spawn_ghosts(new_maze)
        return replace(
            self,
            board=new_board,
            player=replace(self.player, position=Position(*new_maze.center)),
            ghosts=ghosts,
            level_idx=next_idx,
            remaining_time=next_lvl.time,
            screen=Screen.PLAYING,
            error_msg="",
        )

    def lose_life(self) -> GameState:
        """
        Handle the player being touched by a non-edible ghost:
        decrement lives and respawn, or transition to game over.
        """
        new_lives = self.player.lives - 1
        if new_lives == 0:
            return replace(self, player=replace(self.player, lives=0), screen=Screen.GAME_OVER)
        respawned = respawn(self.player, Position(*self.board.maze.center))
        new_player = replace(respawned, lives=new_lives)
        return replace(self, player=new_player, ghosts=_spawn_ghosts(self.board.maze))

    def update(self, dt: float) -> GameState:
        """
        Advance the game by one tick: moves ghosts, checks pacgum and
        ghost collisions, and ticks down the level timer.
        """
        new_remaining = self.remaining_time - dt
        if new_remaining <= 0:
            return replace(
                self,
                player=replace(self.player, lives=0),
                remaining_time=0,
                screen=Screen.GAME_OVER,
            )
        ticks = round(dt * 60)
        new_player = self.player
        new_move_timer = new_player.move_timer - ticks
        if new_move_timer <= 0:
            moved = new_player
            if new_player.desired_direction is not None:
                moved = move(new_player, self.board, new_player.desired_direction)
            if moved.position == new_player.position:
                moved = move(new_player, self.board, new_player.facing_direction)
            if moved.position != new_player.position:
                new_player = replace(moved, move_timer=PLAYER_MOVE_INTERVAL_TICKS)
            else:
                new_player = replace(moved, move_timer=0)
        else:
            new_player = replace(new_player, move_timer=new_move_timer)
        working_ghosts = []
        for g in self.ghosts:
            if g.position == new_player.position:
                match g.mode:
                    case GhostMode.CHASING:
                        return replace(
                            self, remaining_time=new_remaining, player=new_player
                        ).lose_life()
                    case GhostMode.FRIGHTENED:
                        working_ghosts.append(eat_ghost(g))
                        new_player = replace(
                            new_player, score=new_player.score + self.config.points_per_ghost
                        )
                        continue
            working_ghosts.append(g)

        new_ghosts = [
            update_ghost(g, new_player, self.board, dt, working_ghosts) for g in working_ghosts
        ]
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
                            self,
                            board=new_board,
                            player=new_player,
                            ghosts=new_ghosts,
                            remaining_time=new_remaining,
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
        final_state = replace(
            self,
            board=new_board,
            player=new_player,
            ghosts=new_ghosts,
            remaining_time=new_remaining,
        )
        if new_board.is_cleared():
            return final_state.advance_level()
        return final_state
