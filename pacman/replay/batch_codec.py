"""Binary codec for transferring replay batches through shared memory."""

import struct
from enum import Enum

from typed_errs import Err, Ok, Result

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

MAGIC = b"PFRB"
VERSION = 1

HEADER = struct.Struct("!4sBQII")
FRAME = struct.Struct("!QiiBqiBB")
GHOST = struct.Struct("!BiiBB")
CHANGE = struct.Struct("!QQB")


class BatchCodecError(Enum):
    """Failures while encoding or decoding a replay batch."""

    BUFFER_TOO_SMALL = "buffer_too_small"
    INVALID_BUFFER = "invalid_buffer"
    INVALID_VALUE = "invalid_value"
    MALFORMED_BATCH = "malformed_batch"
    INVALID_ENUM = "invalid_enum"
    UNSUPPORTED_VERSION = "unsupported_version"
    TRAILING_DATA = "trailing_data"


def batch_codec_err(error: BatchCodecError) -> Err[BatchCodecError]:
    """Create a consistently contextualized batch-codec error.

    Returns:
        Batch codec error with stable namespace and context.
    """
    return Err(
        error=error,
        namespace="replay_batch_codec",
        context_msg="Failed to process encoded replay batch",
    )


def encoded_batch_size(batch: FrameBatch) -> int:
    """Calculate the exact byte count required by one batch.

    Returns:
        Number of bytes required by ``encode_batch_into``.
    """
    ghost_count = sum(len(frame.ghosts) for frame in batch.frames)
    return (
        HEADER.size
        + len(batch.frames) * FRAME.size
        + ghost_count * GHOST.size
        + len(batch.collectible_changes) * CHANGE.size
    )


def encode_batch_into(
    batch: FrameBatch,
    destination: memoryview,
) -> Result[int, BatchCodecError]:
    """Encode one batch directly into caller-owned contiguous memory.

    Returns:
        Number of bytes written or a typed validation error.
    """
    required = encoded_batch_size(batch)
    try:
        target = destination.cast("B")
    except (TypeError, ValueError):
        return batch_codec_err(BatchCodecError.INVALID_BUFFER)

    try:
        if target.readonly:
            return batch_codec_err(BatchCodecError.INVALID_BUFFER)
        if target.nbytes < required:
            return batch_codec_err(BatchCodecError.BUFFER_TOO_SMALL)

        offset = 0
        HEADER.pack_into(
            target,
            offset,
            MAGIC,
            VERSION,
            int(batch.replay_id),
            len(batch.frames),
            len(batch.collectible_changes),
        )
        offset += HEADER.size

        for frame in batch.frames:
            FRAME.pack_into(
                target,
                offset,
                int(frame.tick),
                int(frame.player.position.x),
                int(frame.player.position.y),
                int(frame.player.direction),
                int(frame.score),
                frame.lives,
                int(frame.phase),
                len(frame.ghosts),
            )
            offset += FRAME.size

            for ghost in frame.ghosts:
                GHOST.pack_into(
                    target,
                    offset,
                    int(ghost.ghost),
                    int(ghost.position.x),
                    int(ghost.position.y),
                    int(ghost.direction),
                    int(ghost.state),
                )
                offset += GHOST.size

        for change in batch.collectible_changes:
            CHANGE.pack_into(
                target,
                offset,
                int(change.tick),
                int(change.tile),
                int(change.collectible),
            )
            offset += CHANGE.size
    except (OverflowError, struct.error, TypeError, ValueError):
        return batch_codec_err(BatchCodecError.INVALID_VALUE)
    finally:
        target.release()

    return Ok(required)


def decode_batch_from(
    source: memoryview,
) -> Result[FrameBatch, BatchCodecError]:
    """Decode one complete batch from contiguous caller-owned memory.

    Returns:
        Immutable replay batch or a typed decoding error.
    """
    try:
        data = source.cast("B")
    except (TypeError, ValueError):
        return batch_codec_err(BatchCodecError.INVALID_BUFFER)

    try:
        return _decode_batch(data)
    finally:
        data.release()


def _decode_batch(data: memoryview) -> Result[FrameBatch, BatchCodecError]:
    """Decode an already validated byte-oriented view.

    Returns:
        Immutable replay batch or a typed decoding error.
    """
    if data.nbytes < HEADER.size:
        return batch_codec_err(BatchCodecError.MALFORMED_BATCH)

    try:
        magic, version, replay_id, frame_count, change_count = HEADER.unpack_from(data, 0)
    except (struct.error, TypeError):
        return batch_codec_err(BatchCodecError.MALFORMED_BATCH)

    if magic != MAGIC:
        return batch_codec_err(BatchCodecError.MALFORMED_BATCH)
    if version != VERSION:
        return batch_codec_err(BatchCodecError.UNSUPPORTED_VERSION)

    minimum_size = HEADER.size + frame_count * FRAME.size + change_count * CHANGE.size
    if minimum_size > data.nbytes:
        return batch_codec_err(BatchCodecError.MALFORMED_BATCH)

    offset = HEADER.size
    frames: list[Frame] = []
    try:
        for _ in range(frame_count):
            tick, x, y, direction, score, lives, phase, ghost_count = FRAME.unpack_from(
                data, offset
            )
            offset += FRAME.size
            ghosts: list[GhostFrame] = []

            for _ in range(ghost_count):
                ghost, ghost_x, ghost_y, ghost_direction, state = GHOST.unpack_from(data, offset)
                offset += GHOST.size
                ghosts.append(
                    GhostFrame(
                        ghost=Ghost(ghost),
                        position=Position(Coord(ghost_x), Coord(ghost_y)),
                        direction=Direction(ghost_direction),
                        state=GhostState(state),
                    )
                )

            frames.append(
                Frame(
                    tick=Tick(tick),
                    player=PlayerFrame(
                        position=Position(Coord(x), Coord(y)),
                        direction=Direction(direction),
                    ),
                    ghosts=tuple(ghosts),
                    score=Score(score),
                    lives=lives,
                    phase=GamePhase(phase),
                )
            )

        changes: list[CollectibleChange] = []
        for _ in range(change_count):
            tick, tile, collectible = CHANGE.unpack_from(data, offset)
            offset += CHANGE.size
            changes.append(
                CollectibleChange(
                    tick=Tick(tick),
                    tile=TileIndex(tile),
                    collectible=Collectible(collectible),
                )
            )
    except ValueError:
        return batch_codec_err(BatchCodecError.INVALID_ENUM)
    except (struct.error, TypeError):
        return batch_codec_err(BatchCodecError.MALFORMED_BATCH)

    if offset != data.nbytes:
        return batch_codec_err(BatchCodecError.TRAILING_DATA)

    return Ok(
        FrameBatch(
            replay_id=ReplayId(replay_id),
            frames=tuple(frames),
            collectible_changes=tuple(changes),
        )
    )
