import os

import pytest
from pacman.analyze.runtime.ipc_protocol import Sequence, TransferId
from pacman.analyze.runtime.shared_batch import (
    SharedBatch,
    SharedBatchError,
    SharedBatchStatus,
)
from pacman.replay.batch_codec import encoded_batch_size
from pacman.replay.models import (
    Coord,
    Direction,
    Frame,
    FrameBatch,
    GamePhase,
    Ghost,
    GhostFrame,
    GhostState,
    PlayerFrame,
    Position,
    ReplayId,
    Score,
    Tick,
)
from typed_errs import Err


def batch() -> FrameBatch:
    return FrameBatch(
        replay_id=ReplayId(9),
        frames=(
            Frame(
                tick=Tick(42),
                player=PlayerFrame(Position(Coord(3), Coord(4)), Direction.RIGHT),
                ghosts=(
                    GhostFrame(
                        Ghost.BLINKY,
                        Position(Coord(5), Coord(4)),
                        Direction.LEFT,
                        GhostState.CHASE,
                    ),
                ),
                score=Score(120),
                lives=2,
                phase=GamePhase.PLAYING,
            ),
        ),
        collectible_changes=(),
    )


def test_shared_batch_owns_encoded_mmap_until_closed() -> None:
    original = batch()
    shared = SharedBatch.create(TransferId(3), Sequence(7), original).unwrap()

    assert shared.status is SharedBatchStatus.WRITABLE
    assert shared.payload_size == encoded_batch_size(original)
    assert shared.decode().unwrap() == original
    os.fstat(shared.fd)

    shared.seal().unwrap()
    assert shared.status is SharedBatchStatus.SEALED
    assert shared.decode().unwrap() == original

    shared.close().unwrap()
    assert shared.status is SharedBatchStatus.CLOSED
    with pytest.raises(OSError):
        os.fstat(shared.fd)


def test_close_is_idempotent() -> None:
    shared = SharedBatch.create(TransferId(1), Sequence(1), batch()).unwrap()

    shared.close().unwrap()
    shared.close().unwrap()

    assert shared.status is SharedBatchStatus.CLOSED


def test_cannot_seal_twice() -> None:
    shared = SharedBatch.create(TransferId(1), Sequence(1), batch()).unwrap()
    shared.seal().unwrap()

    result = shared.seal()
    shared.close().unwrap()

    assert isinstance(result, Err)
    assert result.error is SharedBatchError.INVALID_STATE


def test_cannot_decode_closed_region() -> None:
    shared = SharedBatch.create(TransferId(1), Sequence(1), batch()).unwrap()
    shared.close().unwrap()

    result = shared.decode()

    assert isinstance(result, Err)
    assert result.error is SharedBatchError.INVALID_STATE
