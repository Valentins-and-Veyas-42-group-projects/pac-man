"""Wires config loading, the game engine, and the renderer together."""

import sys
from dataclasses import dataclass, replace

import pygame as pg
from cli_fw import Command, arg
from typed_errs import Err, Ok, Result, catch_bubble

from pacman.analyze.distance_backend import active_distance_backend
from pacman.config import ConfigError, load_config
from pacman.game.state import GameState
from pacman.models import Direction, HighscoreEntry, Screen
from pacman.visualizer.renderer import Renderer


@dataclass
class MainArgs:
    """CLI schema: a single positional config file path."""

    config_path: str = arg(positional=True, help="Path to the JSON (with comments) config file")


@catch_bubble
def run(args: MainArgs) -> Result[None, ConfigError]:
    """Load the config and run the game loop.

    Args:
        args: Parsed CLI arguments (just the config file path).

    Returns:
        Ok(None) on a clean exit, Err on an unrecoverable failure.
    """
    config = load_config(args.config_path).q
    state = GameState.new(
        config,
        highscores=[
            HighscoreEntry(name="AAA", score=100),
        ],
    )
    renderer = Renderer(width=840, height=840)
    renderer.init_window()
    running = True
    clock = pg.time.Clock()
    while running:
        dt = clock.tick(60) / 1000
        events = renderer.handle_input()
        for event in events:
            match event.type:
                case pg.QUIT:
                    running = False
                case pg.KEYDOWN:
                    match state.screen:
                        case Screen.MAIN_MENU:
                            match event.key:
                                # TODO:Remove temp victory and game over warps
                                case pg.K_0:
                                    state = replace(state, screen=Screen.VICTORY)
                                case pg.K_1:
                                    state = replace(state, screen=Screen.GAME_OVER)
                                case pg.K_UP | pg.K_k:
                                    new_selection = (state.menu_selection - 1) % 4
                                    state = replace(state, menu_selection=new_selection)
                                case pg.K_DOWN | pg.K_j:
                                    new_selection = (state.menu_selection + 1) % 4
                                    state = replace(state, menu_selection=new_selection)
                                case pg.K_RETURN:
                                    match state.menu_selection:
                                        case 0:
                                            state = state.start_game()
                                        case 1:
                                            state = replace(state, screen=Screen.HIGHSCORES)
                                        case 2:
                                            state = replace(state, screen=Screen.INSTRUCTIONS)
                                        case 3:
                                            running = False
                        case Screen.INSTRUCTIONS:
                            if event.key == pg.K_ESCAPE:
                                state = replace(state, screen=Screen.MAIN_MENU)
                        case Screen.HIGHSCORES:
                            if event.key == pg.K_ESCAPE:
                                state = replace(state, screen=Screen.MAIN_MENU)
                        case Screen.PLAYING:
                            match event.key:
                                case pg.K_UP | pg.K_k:
                                    new_player = replace(
                                        state.player, desired_direction=Direction.UP
                                    )
                                    state = replace(state, player=new_player)
                                case pg.K_RIGHT | pg.K_l:
                                    new_player = replace(
                                        state.player, desired_direction=Direction.RIGHT
                                    )
                                    state = replace(state, player=new_player)
                                case pg.K_DOWN | pg.K_j:
                                    new_player = replace(
                                        state.player, desired_direction=Direction.DOWN
                                    )
                                    state = replace(state, player=new_player)
                                case pg.K_LEFT | pg.K_h:
                                    new_player = replace(
                                        state.player, desired_direction=Direction.LEFT
                                    )
                                    state = replace(state, player=new_player)
                                case pg.K_ESCAPE | pg.K_p:
                                    state = replace(state, screen=Screen.PAUSED)
                        case Screen.PAUSED:
                            match event.key:
                                case pg.K_UP | pg.K_k:
                                    new_selection = (state.menu_selection - 1) % 2
                                    state = replace(state, menu_selection=new_selection)
                                case pg.K_DOWN | pg.K_j:
                                    new_selection = (state.menu_selection + 1) % 2
                                    state = replace(state, menu_selection=new_selection)
                                case pg.K_RETURN:
                                    match state.menu_selection:
                                        case 0:
                                            state = state.resume()
                                        case 1:
                                            state = replace(state, screen=Screen.MAIN_MENU)
                        case Screen.VICTORY | Screen.GAME_OVER:
                            match event.key:
                                case pg.K_RETURN:
                                    if len(state.name_entry) > 0:
                                        new_score = HighscoreEntry(
                                            name=state.name_entry, score=state.player.score
                                        )
                                        new_list = state.highscores + [new_score]
                                        state = replace(
                                            state, highscores=new_list, screen=Screen.MAIN_MENU
                                        )
                                case pg.K_BACKSPACE:
                                    if len(state.name_entry) > 0:
                                        state = replace(state, name_entry=state.name_entry[:-1])
                                case _:
                                    if event.unicode.isalnum() and len(state.name_entry) < 10:
                                        state = replace(
                                            state, name_entry=state.name_entry + event.unicode
                                        )

        if state.screen is Screen.PLAYING:
            state = state.update(dt)
        renderer.render(state)
    renderer.quit()
    return Ok(None)


def main() -> None:
    """Entry point: `python3 pac-man.py <config.json>`."""
    active_distance_backend()
    root = Command(
        name="pac-man",
        short="A Pac-Man recreation",
        schema=MainArgs,
        run=run,
    )
    result = root.execute(sys.argv[1:])
    match result:
        case Ok(_):
            pass
        case Err() as err:
            err.print_diagnostic()
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:
        print(e)
        sys.exit(1)
