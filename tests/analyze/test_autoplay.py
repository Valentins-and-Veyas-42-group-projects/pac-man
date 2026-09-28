from pacman.analyze.autoplay import choose_action, choose_tactical_action
from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.simulation import SimulationRules
from pacman.replay.maze_codec import encode_collectibles, encode_topology
from pacman.replay.models import (
    Collectible,
    Coord,
    Direction,
    Frame,
    GamePhase,
    Ghost,
    GhostFrame,
    GhostState,
    Maze,
    MazeId,
    PlayerFrame,
    Position,
    Score,
    Tick,
)
from typed_errs import Some


def test_autoplay_chooses_safe_direction_from_replay_frame() -> None:
    maze = Maze(MazeId(1), 3, 1, encode_topology([[13, 5, 7]]).unwrap(), b"", b"autoplay")
    graph = build_maze_graph(maze).unwrap()
    frame = Frame(
        tick=Tick(0),
        player=PlayerFrame(Position(Coord(1), Coord(0)), Direction.RIGHT),
        ghosts=(
            GhostFrame(
                Ghost.BLINKY,
                Position(Coord(2), Coord(0)),
                Direction.LEFT,
                GhostState.CHASE,
            ),
        ),
        score=Score(0),
        lives=3,
        phase=GamePhase.PLAYING,
    )

    assert choose_action(graph, maze, frame, horizon=2).unwrap() == Some(Direction.LEFT)


def test_tactical_autoplay_chooses_the_scoring_branch() -> None:
    maze = Maze(
        MazeId(2), 3, 1, encode_topology([[13, 5, 7]]).unwrap(),
        encode_collectibles([Collectible.NONE, Collectible.NONE, Collectible.POWER_PELLET]).unwrap(),
        b"tactical-autoplay",
    )
    graph = build_maze_graph(maze).unwrap()
    frame = Frame(
        Tick(0), PlayerFrame(Position(Coord(1), Coord(0)), Direction.RIGHT),
        (), Score(0), 3, GamePhase.PLAYING,
    )

    assert choose_tactical_action(
        graph, maze, (), frame, SimulationRules(horizon_ticks=1)
    ).unwrap() == Some(Direction.RIGHT)
