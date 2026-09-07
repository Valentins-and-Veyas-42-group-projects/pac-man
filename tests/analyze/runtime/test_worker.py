from pacman.analyze.messages import DecisionEvaluationQueued, TurnObserved
from pacman.analyze.runtime.worker import (
    AnalysisOffer,
    AnalysisWorker,
    AnalysisWorkerError,
    WorkerStatus,
)
from pacman.analyze.simulation import SimulationRules
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import (
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
)
from typed_errs import Err


def maze() -> Maze:
    return Maze(
        MazeId(1),
        3,
        1,
        encode_topology([[13, 5, 7]]).unwrap(),
        bytes([0]),
        b"worker-test",
    )


def batch(tick: int, direction: Direction = Direction.RIGHT) -> FrameBatch:
    frame = Frame(
        Tick(tick),
        PlayerFrame(Position(Coord(1), Coord(0)), direction),
        (),
        Score(0),
        3,
        GamePhase.PLAYING,
    )
    return FrameBatch(ReplayId(7), (frame,), ())


def test_worker_processes_batches_and_preserves_messages_through_close() -> None:
    worker = AnalysisWorker.create(maze(), SimulationRules(), queue_capacity=8).unwrap()

    worker.start().unwrap()
    assert worker.offer(batch(10)) is AnalysisOffer.ACCEPTED
    assert worker.offer(batch(11, Direction.DOWN)) is AnalysisOffer.ACCEPTED
    assert worker.offer(batch(41, Direction.DOWN)) is AnalysisOffer.ACCEPTED
    worker.close().unwrap()

    assert worker.status is WorkerStatus.CLOSED
    assert worker.drain() == (
        TurnObserved(ReplayId(7), Tick(11)),
        DecisionEvaluationQueued(ReplayId(7), Tick(11), Tick(41)),
    )


def test_worker_rejects_invalid_capacity() -> None:
    result = AnalysisWorker.create(maze(), SimulationRules(), queue_capacity=0)

    assert isinstance(result, Err)
    assert result.error is AnalysisWorkerError.INVALID_QUEUE_CAPACITY


def test_unstarted_worker_closes_idempotently() -> None:
    worker = AnalysisWorker.create(maze(), SimulationRules()).unwrap()

    worker.close().unwrap()
    worker.close().unwrap()

    assert worker.status is WorkerStatus.CLOSED
    assert worker.offer(batch(10)) is AnalysisOffer.CLOSED
