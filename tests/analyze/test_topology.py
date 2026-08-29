from pacman.analyze.models import MazeGraph, Move
from pacman.analyze.topology import TileKind, classify_tile
from pacman.replay.models import Direction, TileIndex
from typed_errs import Nothing, Some


def topology_graph() -> MazeGraph:
    return MazeGraph(
        width=5,
        height=1,
        moves=(
            (),
            (Move(TileIndex(0), Direction.LEFT),),
            (
                Move(TileIndex(0), Direction.UP),
                Move(TileIndex(1), Direction.DOWN),
            ),
            (
                Move(TileIndex(0), Direction.UP),
                Move(TileIndex(1), Direction.RIGHT),
            ),
            (
                Move(TileIndex(0), Direction.UP),
                Move(TileIndex(1), Direction.RIGHT),
                Move(TileIndex(2), Direction.DOWN),
            ),
        ),
    )


def test_classify_tile_identifies_local_topology() -> None:
    graph = topology_graph()

    assert classify_tile(graph, TileIndex(1)) == Some(TileKind.DEAD_END)
    assert classify_tile(graph, TileIndex(2)) == Some(TileKind.CORRIDOR)
    assert classify_tile(graph, TileIndex(3)) == Some(TileKind.CORNER)
    assert classify_tile(graph, TileIndex(4)) == Some(TileKind.INTERSECTION)


def test_classify_tile_returns_nothing_for_isolated_or_invalid_tiles() -> None:
    graph = topology_graph()

    assert isinstance(classify_tile(graph, TileIndex(0)), Nothing)
    assert isinstance(classify_tile(graph, TileIndex(-1)), Nothing)
    assert isinstance(classify_tile(graph, TileIndex(5)), Nothing)
