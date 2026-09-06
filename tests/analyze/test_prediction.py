from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.prediction import (
    PredictionError,
    build_predicted_threat_field,
    predict_ghost,
)
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import (
    Coord,
    Direction,
    Ghost,
    GhostFrame,
    GhostState,
    Maze,
    MazeId,
    Position,
    TileIndex,
)
from typed_errs import Err


def corridor(cells: list[int]) -> Maze:
    return Maze(
        MazeId(1),
        len(cells),
        1,
        encode_topology([cells]).unwrap(),
        b"",
        b"prediction-test",
    )


def ghost(tile: int, direction: Direction, state: GhostState = GhostState.CHASE) -> GhostFrame:
    return GhostFrame(
        Ghost.BLINKY,
        Position(Coord(tile), Coord(0)),
        direction,
        state,
    )


def test_prediction_continues_forward_instead_of_reversing() -> None:
    maze = corridor([13, 5, 7])
    graph = build_maze_graph(maze).unwrap()

    prediction = predict_ghost(graph, maze, ghost(1, Direction.RIGHT), 1).unwrap()

    assert tuple(state.tile for state in prediction.ticks[1]) == (TileIndex(2),)


def test_prediction_reverses_at_dead_end() -> None:
    maze = corridor([13, 5, 7])
    graph = build_maze_graph(maze).unwrap()

    prediction = predict_ghost(graph, maze, ghost(2, Direction.RIGHT), 1).unwrap()

    assert tuple(state.tile for state in prediction.ticks[1]) == (TileIndex(1),)
    assert prediction.ticks[1][0].direction is Direction.LEFT


def test_prediction_uses_wraparound_tunnel() -> None:
    maze = corridor([5, 5, 5])
    graph = build_maze_graph(maze).unwrap()

    prediction = predict_ghost(graph, maze, ghost(0, Direction.LEFT), 1).unwrap()

    assert tuple(state.tile for state in prediction.ticks[1]) == (TileIndex(2),)


def test_threat_field_ignores_nonlethal_ghosts() -> None:
    maze = corridor([13, 5, 7])
    graph = build_maze_graph(maze).unwrap()

    field = build_predicted_threat_field(
        graph,
        maze,
        (ghost(0, Direction.RIGHT), ghost(2, Direction.LEFT, GhostState.FRIGHTENED)),
        2,
    ).unwrap()

    assert field.etas == (0, 1, 2)
    assert field.owners(TileIndex(2)) == (Ghost.BLINKY,)


def test_prediction_rejects_negative_horizon() -> None:
    maze = corridor([13, 5, 7])
    result = predict_ghost(
        build_maze_graph(maze).unwrap(),
        maze,
        ghost(0, Direction.RIGHT),
        -1,
    )

    assert isinstance(result, Err)
    assert result.error is PredictionError.INVALID_HORIZON
