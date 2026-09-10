from pacman.analyze.distance_backend import distances
from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.models import (
    MazeGraph,
    Move,
    PathfindingError,
)
from pacman.analyze.pathfinding import bfs, distance_to, shortest_path
from pacman.analyze.wasm_pathfinding import WasmPathfinding
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import (
    Direction,
    Maze,
    MazeId,
    TileIndex,
)
from typed_errs import Err, Nothing, Some


def branching_graph() -> MazeGraph:
    return MazeGraph(
        width=3,
        height=2,
        moves=(
            (Move(TileIndex(1), Direction.RIGHT),),
            (
                Move(TileIndex(0), Direction.LEFT),
                Move(TileIndex(2), Direction.RIGHT),
                Move(TileIndex(4), Direction.DOWN),
            ),
            (Move(TileIndex(1), Direction.LEFT),),
            (),
            (Move(TileIndex(1), Direction.UP),),
            (),
        ),
    )


def test_bfs_calculates_shortest_distances_and_leaves_disconnected_tiles() -> None:
    field = bfs(branching_graph(), TileIndex(0)).unwrap()

    assert field.distances == (0, 1, 2, -1, 2, -1)
    assert distance_to(field, TileIndex(0)) == Some(0)
    assert distance_to(field, TileIndex(4)) == Some(2)
    assert isinstance(distance_to(field, TileIndex(3)), Nothing)


def test_optional_distance_backend_matches_python_bfs() -> None:
    graph = branching_graph()

    assert distances(graph, TileIndex(0)).unwrap() == bfs(graph, TileIndex(0)).unwrap().distances


def test_wasm_bridge_backend_matches_python_bfs() -> None:
    class TestBridge:
        created = 0

        def createTopology(self, encoded: list[int], tile_count: int, width: int) -> int:
            assert len(encoded) == tile_count * 18
            assert width == 3
            self.created += 1
            return 42

        def destroyTopology(self, topology: int) -> None:
            assert topology == 42

        def topologyBfsDistances(self, topology: int, tile_count: int, origin: int) -> list[int]:
            assert topology == 42
            assert tile_count == 6
            assert origin == 0
            return [0, 1, 2, -1, 2, -1]

        def bfsDistances(self, encoded: list[int], tile_count: int, width: int, origin: int) -> list[int]:
            assert tile_count == 6
            assert width == 3
            assert origin == 0
            assert len(encoded) == tile_count * 18
            return [0, 1, 2, -1, 2, -1]

    bridge = TestBridge()
    backend = WasmPathfinding(bridge)
    graph = branching_graph()

    assert backend.distances(graph, TileIndex(0)) == Some((0, 1, 2, -1, 2, -1))
    assert backend.distances(graph, TileIndex(0)) == Some((0, 1, 2, -1, 2, -1))
    assert bridge.created == 1


def test_bfs_rejects_origins_outside_the_graph() -> None:
    for origin in (TileIndex(-1), TileIndex(6)):
        result = bfs(branching_graph(), origin)
        assert isinstance(result, Err)
        assert result.error is PathfindingError.INVALID_ORIGIN


def test_bfs_uses_graph_built_from_persisted_topology() -> None:
    topology = encode_topology([[13, 5, 7]]).unwrap()
    maze = Maze(
        id=MazeId(1),
        width=3,
        height=1,
        topology=topology,
        initial_collectibles=b"",
        checksum=b"pathfinding-test",
    )
    graph = build_maze_graph(maze).unwrap()
    field = bfs(graph, TileIndex(0)).unwrap()

    assert field.distances == (0, 1, 2)
    assert distance_to(field, TileIndex(2)) == Some(2)
    assert isinstance(distance_to(field, TileIndex(3)), Nothing)


def test_shortest_path_reconstructs_route() -> None:
    field = bfs(branching_graph(), TileIndex(0)).unwrap()
    path = shortest_path(field, TileIndex(4)).unwrap()

    assert path.tiles == (
        TileIndex(0),
        TileIndex(1),
        TileIndex(4),
    )
    assert path.distance == 2


def test_shortest_path_from_origin_to_itself() -> None:
    field = bfs(branching_graph(), TileIndex(0)).unwrap()
    path = shortest_path(field, TileIndex(0)).unwrap()

    assert path.tiles == (TileIndex(0),)
    assert path.distance == 0


def test_shortest_path_returns_nothing_when_destination_is_unavailable() -> None:
    field = bfs(branching_graph(), TileIndex(0)).unwrap()

    assert isinstance(shortest_path(field, TileIndex(3)), Nothing)
    assert isinstance(shortest_path(field, TileIndex(-1)), Nothing)
    assert isinstance(shortest_path(field, TileIndex(6)), Nothing)
