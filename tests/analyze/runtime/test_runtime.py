from pacman.analyze.messages import (
    DeathQueued,
    DecisionEvaluationQueued,
    TurnObserved,
)
from pacman.analyze.runtime.runtime import AnalysisRuntime, AnalysisRuntimeError
from pacman.analyze.simulation import SimulationRules
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import (
    Collectible,
    CollectibleChange,
    Coord,
    Direction,
    Frame,
    FrameBatch,
    GamePhase,
    Maze,
    MazeId,
    PlayerFrame,
    Position,
    ReplayId,
    Score,
    Tick,
    TileIndex,
)
from typed_errs import Err


def maze() -> Maze:
    return Maze(
        MazeId(1),
        3,
        1,
        encode_topology([[13, 5, 7]]).unwrap(),
        bytes([0]),
        b"runtime-test",
    )


def frame(
    tick: int,
    direction: Direction = Direction.RIGHT,
    phase: GamePhase = GamePhase.PLAYING,
) -> Frame:
    return Frame(
        Tick(tick),
        PlayerFrame(Position(Coord(1), Coord(0)), direction),
        (),
        Score(0),
        3,
        phase,
    )


def batch(replay_id: int, *frames: Frame) -> FrameBatch:
    return FrameBatch(ReplayId(replay_id), frames, ())


def test_consume_drives_turn_and_death_analyzers_across_batches() -> None:
    runtime = AnalysisRuntime.create(maze(), SimulationRules()).unwrap()

    assert runtime.consume(batch(7, frame(10))).unwrap() == ()
    assert runtime.consume(batch(7, frame(11, Direction.DOWN))).unwrap() == (
        TurnObserved(ReplayId(7), Tick(11)),
    )
    assert runtime.consume(batch(7, frame(12, Direction.DOWN, GamePhase.DYING))).unwrap() == (
        DeathQueued(ReplayId(7), Tick(12)),
    )
    assert runtime.consume(batch(7, frame(13, Direction.DOWN, GamePhase.DYING))).unwrap() == ()


def test_turn_evaluation_is_emitted_after_thirty_replay_ticks() -> None:
    runtime = AnalysisRuntime.create(maze(), SimulationRules()).unwrap()
    runtime.consume(batch(7, frame(10))).unwrap()

    turned = runtime.consume(batch(7, frame(11, Direction.DOWN))).unwrap()
    before_deadline = runtime.consume(batch(7, frame(40, Direction.DOWN))).unwrap()
    at_deadline = runtime.consume(batch(7, frame(41, Direction.DOWN))).unwrap()

    assert TurnObserved(ReplayId(7), Tick(11)) in turned
    assert before_deadline == ()
    assert at_deadline == (
        DecisionEvaluationQueued(
            replay_id=ReplayId(7),
            decision_tick=Tick(11),
            evaluation_tick=Tick(41),
        ),
    )


def test_consume_updates_bounded_incremental_state() -> None:
    runtime = AnalysisRuntime.create(maze(), SimulationRules(), recent_capacity=2).unwrap()
    change = CollectibleChange(Tick(11), TileIndex(1), Collectible.NONE)

    runtime.consume(FrameBatch(ReplayId(7), (frame(10), frame(11)), (change,))).unwrap()
    runtime.consume(batch(7, frame(12))).unwrap()

    assert tuple(value.tick for value in runtime.state.recent_frames) == (Tick(11), Tick(12))
    assert runtime.state.collectible_changes == [change]


def test_consume_rejects_a_different_replay_without_mutating_state() -> None:
    runtime = AnalysisRuntime.create(maze(), SimulationRules()).unwrap()
    runtime.consume(batch(7, frame(10))).unwrap()

    result = runtime.consume(batch(8, frame(11)))

    assert isinstance(result, Err)
    assert result.error is AnalysisRuntimeError.WRONG_REPLAY
    assert tuple(value.tick for value in runtime.state.recent_frames) == (Tick(10),)


def test_consume_rejects_ticks_older_than_the_runtime_clock() -> None:
    runtime = AnalysisRuntime.create(maze(), SimulationRules()).unwrap()
    runtime.consume(batch(7, frame(10))).unwrap()

    result = runtime.consume(batch(7, frame(9)))

    assert isinstance(result, Err)
    assert result.error is AnalysisRuntimeError.TICK_MOVED_BACKWARDS
    assert tuple(value.tick for value in runtime.state.recent_frames) == (Tick(10),)


def test_create_rejects_nonpositive_step_budget() -> None:
    result = AnalysisRuntime.create(maze(), SimulationRules(), step_budget=0)

    assert isinstance(result, Err)
    assert result.error is AnalysisRuntimeError.INVALID_STEP_BUDGET
