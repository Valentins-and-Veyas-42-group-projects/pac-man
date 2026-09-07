from pacman.analyze.models import MazeGraph
from pacman.analyze.runtime.state import RuntimeState, RuntimeStateError
from pacman.analyze.simulation import SimulationRules
from pacman.replay.models import Maze, MazeId
from typed_errs import Err


def maze(width: int = 2, height: int = 1) -> Maze:
    return Maze(MazeId(1), width, height, b"", b"", b"runtime-state-test")


def graph(width: int = 2, height: int = 1, nodes: int = 2) -> MazeGraph:
    return MazeGraph(width, height, tuple(() for _ in range(nodes)))


def test_create_allocates_bounded_empty_runtime_storage() -> None:
    state = RuntimeState.create(maze(), graph(), SimulationRules(), recent_capacity=3).unwrap()

    assert state.recent_frames.maxlen == 3
    assert tuple(state.recent_frames) == ()
    assert state.collectible_changes == []
    assert state.evaluations == []


def test_create_rejects_nonpositive_capacity() -> None:
    result = RuntimeState.create(maze(), graph(), SimulationRules(), recent_capacity=0)

    assert isinstance(result, Err)
    assert result.error is RuntimeStateError.INVALID_RECENT_CAPACITY


def test_create_rejects_graph_dimensions_from_another_maze() -> None:
    result = RuntimeState.create(
        maze(), graph(width=1, height=2), SimulationRules(), recent_capacity=3
    )

    assert isinstance(result, Err)
    assert result.error is RuntimeStateError.DIMENSION_MISMATCH


def test_create_rejects_incorrect_graph_node_count() -> None:
    result = RuntimeState.create(maze(), graph(nodes=1), SimulationRules(), recent_capacity=3)

    assert isinstance(result, Err)
    assert result.error is RuntimeStateError.NODE_COUNT_MISMATCH
