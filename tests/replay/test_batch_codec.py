import struct

from pacman.replay.batch_codec import (
    HEADER,
    VERSION,
    BatchCodecError,
    decode_batch_from,
    encode_batch_into,
    encoded_batch_size,
)
from pacman.replay.models import (
    Collectible,
    CollectibleChange,
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
    TileIndex,
)
from typed_errs import Err


def batch() -> FrameBatch:
    return FrameBatch(
        replay_id=ReplayId(7),
        frames=(
            Frame(
                tick=Tick(100),
                player=PlayerFrame(Position(Coord(10), Coord(11)), Direction.RIGHT),
                ghosts=(
                    GhostFrame(
                        Ghost.BLINKY,
                        Position(Coord(14), Coord(11)),
                        Direction.LEFT,
                        GhostState.CHASE,
                    ),
                    GhostFrame(
                        Ghost.INKY,
                        Position(Coord(8), Coord(4)),
                        Direction.DOWN,
                        GhostState.FRIGHTENED,
                    ),
                ),
                score=Score(1230),
                lives=3,
                phase=GamePhase.PLAYING,
            ),
            Frame(
                tick=Tick(101),
                player=PlayerFrame(Position(Coord(11), Coord(11)), Direction.DOWN),
                ghosts=(),
                score=Score(1240),
                lives=2,
                phase=GamePhase.DYING,
            ),
        ),
        collectible_changes=(
            CollectibleChange(Tick(100), TileIndex(31), Collectible.NONE),
            CollectibleChange(Tick(101), TileIndex(44), Collectible.POWER_PELLET),
        ),
    )


def encode(value: FrameBatch) -> bytearray:
    storage = bytearray(encoded_batch_size(value))
    written = encode_batch_into(value, memoryview(storage)).unwrap()

    assert written == len(storage)
    return storage


def test_batch_round_trips_through_memoryview() -> None:
    original = batch()

    decoded = decode_batch_from(memoryview(encode(original))).unwrap()

    assert decoded == original


def test_empty_batch_round_trips() -> None:
    original = FrameBatch(ReplayId(0), (), ())

    decoded = decode_batch_from(memoryview(encode(original))).unwrap()

    assert decoded == original


def test_encode_rejects_small_and_readonly_buffers() -> None:
    original = batch()
    too_small = encode_batch_into(original, memoryview(bytearray(encoded_batch_size(original) - 1)))
    readonly = encode_batch_into(original, memoryview(bytes(encoded_batch_size(original))))

    assert isinstance(too_small, Err)
    assert too_small.error is BatchCodecError.BUFFER_TOO_SMALL
    assert isinstance(readonly, Err)
    assert readonly.error is BatchCodecError.INVALID_BUFFER


def test_decode_rejects_truncated_and_trailing_data() -> None:
    encoded = encode(batch())

    truncated = decode_batch_from(memoryview(encoded[:-1]))
    trailing = decode_batch_from(memoryview(encoded + b"extra"))

    assert isinstance(truncated, Err)
    assert truncated.error is BatchCodecError.MALFORMED_BATCH
    assert isinstance(trailing, Err)
    assert trailing.error is BatchCodecError.TRAILING_DATA


def test_decode_rejects_unknown_version() -> None:
    encoded = encode(batch())
    encoded[4] = VERSION + 1

    result = decode_batch_from(memoryview(encoded))

    assert isinstance(result, Err)
    assert result.error is BatchCodecError.UNSUPPORTED_VERSION


def test_decode_rejects_invalid_frame_enum() -> None:
    encoded = encode(batch())
    direction_offset = HEADER.size + struct_offset("!Qii")
    encoded[direction_offset] = 255

    result = decode_batch_from(memoryview(encoded))

    assert isinstance(result, Err)
    assert result.error is BatchCodecError.INVALID_ENUM


def struct_offset(format_: str) -> int:
    return struct.calcsize(format_)
