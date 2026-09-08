from pacman.analyze.decision import analyze_decision
from pacman.analyze.evaluation import PlayQuality
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


def test_decision_analysis_composes_counterfactual_stages() -> None:
    maze = Maze(
        MazeId(1),
        3,
        2,
        encode_topology([[9, 5, 7], [12, 5, 7]]).unwrap(),
        encode_collectibles([
            Collectible.NONE,
            Collectible.PACGUM,
            Collectible.NONE,
            Collectible.PACGUM,
            Collectible.PACGUM,
            Collectible.NONE,
        ]).unwrap(),
        b"decision-test",
    )
    frame = Frame(
        Tick(100),
        PlayerFrame(Position(Coord(0), Coord(0)), Direction.RIGHT),
        (
            GhostFrame(
                Ghost.BLINKY,
                Position(Coord(2), Coord(0)),
                Direction.LEFT,
                GhostState.CHASE,
            ),
        ),
        Score(0),
        3,
        GamePhase.PLAYING,
    )

    result = analyze_decision(
        build_maze_graph(maze).unwrap(),
        maze,
        (),
        frame,
        Direction.RIGHT,
        SimulationRules(horizon_ticks=3),
    ).unwrap()

    assert result.evaluation.quality is PlayQuality.BLUNDER
    assert result.evaluation.best.action is Direction.DOWN
