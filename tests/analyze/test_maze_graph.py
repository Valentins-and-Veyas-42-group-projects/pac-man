from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.pathfinding import bfs, shortest_path
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import Direction, Maze, MazeId, TileIndex


def maze_from_cells(cells: list[list[int]]) -> Maze:
    return Maze(
        id=MazeId(1),
        width=len(cells[0]),
        height=len(cells),
        topology=encode_topology(cells).unwrap(),
        initial_collectibles=b"",
        checksum=b"maze-graph-test",
    )


def test_matching_open_boundaries_create_horizontal_wraparound() -> None:
    graph = build_maze_graph(maze_from_cells([[5, 5, 5]])).unwrap()

    left_wrap = next(
        move for move in graph.neighbors(TileIndex(0)) if move.direction is Direction.LEFT
    )
    right_wrap = next(
        move for move in graph.neighbors(TileIndex(2)) if move.direction is Direction.RIGHT
    )

    assert left_wrap.destination == TileIndex(2)
    assert left_wrap.wraparound
    assert right_wrap.destination == TileIndex(0)
    assert right_wrap.wraparound
    path = shortest_path(bfs(graph, TileIndex(0)).unwrap(), TileIndex(2)).unwrap()
    assert path.tiles == (TileIndex(0), TileIndex(2))


def test_unmatched_boundary_opening_does_not_create_wraparound() -> None:
    graph = build_maze_graph(maze_from_cells([[5, 7]])).unwrap()

    assert not any(move.wraparound for moves in graph.moves for move in moves)
