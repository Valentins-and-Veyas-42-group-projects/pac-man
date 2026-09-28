from pathlib import Path

from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.replay_report import analyze_replay, analyze_saved_replay
from pacman.analyze.simulation import SimulationRules
from pacman.replay.maze_codec import encode_collectibles, encode_topology
from pacman.replay.models import (
    Collectible,
    Coord,
    Direction,
    EncodedMaze,
    Frame,
    FrameBatch,
    GamePhase,
    Maze,
    MazeId,
    PlayerFrame,
    Position,
    Score,
    Tick,
)
from pacman.replay.store import ReplayStore
from typed_errs import Nothing, Some


def test_report_links_death_to_preceding_turn() -> None:
    maze = Maze(
        MazeId(1),
        3,
        2,
        encode_topology([[9, 5, 7], [12, 5, 7]]).unwrap(),
        encode_collectibles([Collectible.NONE] * 6).unwrap(),
        b"report-test",
    )
    graph = build_maze_graph(maze).unwrap()
    frames = (
        Frame(Tick(0), PlayerFrame(Position(Coord(0), Coord(0)), Direction.RIGHT), (), Score(0), 3, GamePhase.PLAYING),
        Frame(Tick(1), PlayerFrame(Position(Coord(0), Coord(0)), Direction.DOWN), (), Score(0), 3, GamePhase.PLAYING),
        Frame(Tick(2), PlayerFrame(Position(Coord(0), Coord(1)), Direction.DOWN), (), Score(0), 2, GamePhase.DYING),
    )

    report = analyze_replay(graph, maze, frames, (), SimulationRules(horizon_ticks=1)).unwrap()

    assert len(report.decisions) == 1
    assert report.decisions[0].played_action is Direction.DOWN
    assert len(report.summary.decisions) == 1
    assert report.deaths[0].tick == Tick(2)
    assert report.deaths[0].preceding_decision == Some(report.decisions[0])


def test_saved_report_uses_recorded_frames(tmp_path: Path) -> None:
    store = ReplayStore(tmp_path / "report.sqlite3")
    store.initialize_replay().unwrap()
    topology = encode_topology([[9, 5, 7], [12, 5, 7]]).unwrap()
    items = encode_collectibles([Collectible.NONE] * 6).unwrap()
    maze_id = store.create_maze(EncodedMaze(3, 2, (0, 0), (2, 1), topology, items, b"saved-report")).unwrap()
    replay_id = store.create_replay(maze_id, 60, 1, 1, b"config", 7).unwrap()
    frames = (
        Frame(Tick(0), PlayerFrame(Position(Coord(0), Coord(0)), Direction.RIGHT), (), Score(0), 3, GamePhase.PLAYING),
        Frame(Tick(1), PlayerFrame(Position(Coord(0), Coord(0)), Direction.DOWN), (), Score(0), 3, GamePhase.PLAYING),
        Frame(Tick(2), PlayerFrame(Position(Coord(0), Coord(1)), Direction.DOWN), (), Score(0), 2, GamePhase.DYING),
    )
    store.append(FrameBatch(replay_id, frames, ())).unwrap()

    report = analyze_saved_replay(store, replay_id, SimulationRules(horizon_ticks=1)).unwrap()

    assert len(report.decisions) == 1
    assert report.deaths[0].tick == Tick(2)


def test_sparse_frames_report_unreconstructable_turn() -> None:
    maze = Maze(
        MazeId(3),
        3,
        1,
        encode_topology([[13, 5, 7]]).unwrap(),
        encode_collectibles([Collectible.NONE] * 3).unwrap(),
        b"sparse-report",
    )
    graph = build_maze_graph(maze).unwrap()
    frames = (
        Frame(Tick(0), PlayerFrame(Position(Coord(0), Coord(0)), Direction.RIGHT), (), Score(0), 3, GamePhase.PLAYING),
        Frame(Tick(30), PlayerFrame(Position(Coord(2), Coord(0)), Direction.LEFT), (), Score(0), 3, GamePhase.PLAYING),
        Frame(Tick(31), PlayerFrame(Position(Coord(1), Coord(0)), Direction.LEFT), (), Score(0), 2, GamePhase.DYING),
    )

    report = analyze_replay(graph, maze, frames, (), SimulationRules(horizon_ticks=1)).unwrap()

    assert report.decisions == ()
    assert report.unevaluated_turns == (Tick(30),)
    assert report.deaths[0].preceding_decision == Nothing()
