from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.models import MazeGraph, Move
from pacman.analyze.state import AnalysisStateError, analyze_frame
from pacman.analyze.topology import TileKind
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import (
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
    TileIndex,
)
from typed_errs import Err


def corridor_maze() -> Maze:
    return Maze(
        id=MazeId(1),
        width=3,
        height=1,
        topology=encode_topology([[13, 5, 7]]).unwrap(),
        initial_collectibles=b"",
        checksum=b"state-test",
    )


def frame(
    player: Position | None = None,
    ghosts: tuple[GhostFrame, ...] | None = None,
) -> Frame:
    if player is None:
        player = Position(Coord(1), Coord(0))
    if ghosts is None:
        ghosts = (
            GhostFrame(
                Ghost.BLINKY,
                Position(Coord(0), Coord(0)),
                Direction.RIGHT,
                GhostState.CHASE,
            ),
            GhostFrame(
                Ghost.INKY,
                Position(Coord(2), Coord(0)),
                Direction.LEFT,
                GhostState.FRIGHTENED,
            ),
        )
    return Frame(
        Tick(10),
        PlayerFrame(player, Direction.RIGHT),
        ghosts,
        Score(100),
        3,
        GamePhase.PLAYING,
    )


def test_analyze_frame_reconstructs_tactical_state() -> None:
    maze = corridor_maze()
    graph = build_maze_graph(maze).unwrap()
    state = analyze_frame(graph, maze, frame()).unwrap()

    assert state.tick == Tick(10)
    assert state.player_tile == TileIndex(1)
    assert state.legal_actions == (Direction.RIGHT, Direction.LEFT)
    assert state.tile_kind is TileKind.CORRIDOR
    assert tuple(
        (distance.ghost, distance.tile, distance.distance, distance.dangerous)
        for distance in state.ghost_distances
    ) == (
        (Ghost.BLINKY, TileIndex(0), 1, True),
        (Ghost.INKY, TileIndex(2), 1, False),
    )


def test_analyze_frame_rejects_player_outside_maze() -> None:
    maze = corridor_maze()
    graph = build_maze_graph(maze).unwrap()
    result = analyze_frame(
        graph,
        maze,
        frame(player=Position(Coord(-1), Coord(0))),
    )

    assert isinstance(result, Err)
    assert result.error is AnalysisStateError.INVALID_PLAYER_TILE


def test_analyze_frame_rejects_ghost_outside_maze() -> None:
    maze = corridor_maze()
    graph = build_maze_graph(maze).unwrap()
    ghosts = (
        GhostFrame(
            Ghost.BLINKY,
            Position(Coord(3), Coord(0)),
            Direction.LEFT,
            GhostState.CHASE,
        ),
    )
    result = analyze_frame(graph, maze, frame(ghosts=ghosts))

    assert isinstance(result, Err)
    assert result.error is AnalysisStateError.INVALID_GHOST_TILE


def test_analyze_frame_rejects_unclassified_player_tile() -> None:
    maze = Maze(
        MazeId(1),
        1,
        1,
        encode_topology([[15]]).unwrap(),
        b"",
        b"isolated",
    )
    graph = build_maze_graph(maze).unwrap()
    result = analyze_frame(
        graph,
        maze,
        frame(player=Position(Coord(0), Coord(0)), ghosts=()),
    )

    assert isinstance(result, Err)
    assert result.error is AnalysisStateError.UNCLASSIFIED_PLAYER_TILE


def test_analyze_frame_rejects_unreachable_ghost() -> None:
    maze = corridor_maze()
    graph = MazeGraph(
        width=3,
        height=1,
        moves=(
            (Move(TileIndex(1), Direction.RIGHT),),
            (Move(TileIndex(0), Direction.LEFT),),
            (),
        ),
    )
    ghosts = (
        GhostFrame(
            Ghost.CLYDE,
            Position(Coord(2), Coord(0)),
            Direction.LEFT,
            GhostState.SCATTER,
        ),
    )
    result = analyze_frame(
        graph,
        maze,
        frame(player=Position(Coord(0), Coord(0)), ghosts=ghosts),
    )

    assert isinstance(result, Err)
    assert result.error is AnalysisStateError.UNREACHABLE_GHOST
