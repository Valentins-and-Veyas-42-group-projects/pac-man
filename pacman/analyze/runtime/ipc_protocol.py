"""Typed binary control protocol for analysis IPC."""

import struct
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import NewType, TypeAlias

from typed_errs import Err, Ok, Result

from pacman.analyze.messages import AnalysisMessage
from pacman.analyze.runtime.runtime import AnalysisRuntimeError

TransferId = NewType("TransferId", int)
Sequence = NewType("Sequence", int)


@dataclass(frozen=True, slots=True)
class AnalyzeBatch:
    """Describe one shared-memory replay batch offered to the worker."""

    transfer_id: TransferId
    sequence: Sequence
    payload_size: int


@dataclass(frozen=True, slots=True)
class StopWorker:
    """Request graceful worker shutdown."""


WorkerCommand: TypeAlias = AnalyzeBatch | StopWorker


@dataclass(frozen=True, slots=True)
class BatchReleased:
    """Confirm that the worker no longer reads one shared batch."""

    transfer_id: TransferId
    sequence: Sequence


@dataclass(frozen=True, slots=True)
class AnalysisProduced:
    """Return analysis messages associated with one input sequence."""

    sequence: Sequence
    messages: tuple[AnalysisMessage, ...]


@dataclass(frozen=True, slots=True)
class WorkerFailed:
    """Report a typed analysis-runtime failure to the parent."""

    error: AnalysisRuntimeError


WorkerOutput: TypeAlias = BatchReleased | AnalysisProduced | WorkerFailed


class IpcProtocolError(Enum):
    """Failures while encoding or decoding IPC control messages."""

    UNKNOWN_MESSAGE = "unknown_message"
    INVALID_PAYLOAD_SIZE = "invalid_payload_size"
    INVALID_TRANSFER_ID = "invalid_transfer_id"
    INVALID_SEQUENCE = "invalid_sequence"
    MALFORMED_MESSAGE = "malformed_message"


class MessageTag(IntEnum):
    """Stable numeric tags encoded into IPC headers."""

    ANALYZE_BATCH = 1
    STOP_WORKER = 2
    BATCH_RELEASED = 3
    ANALYSIS_PRODUCED = 4
    WORKER_FAILED = 5


# Binary layout used for each IPC header:
#
#   ! B Q Q Q
#   │ │ │ │ │
#   │ │ │ │ └─ third value:  u64
#   │ │ │ └─── second value: u64
#   │ │ └───── first value:  u64
#   │ └─────── message tag:  u8
#   └───────── big-endian / network byte order
#
# total size:
#
#   1 + 8 + 8 + 8 = 25 bytes
#
# meaning of the three u64 values depends on the message tag:
#
# ANALYZE_BATCH:
#   value1 = transfer_id
#   value2 = sequence
#   value3 = payload_size
#
# STOP_WORKER:
#   value1 = 0
#   value2 = 0
#   value3 = 0
HEADER = struct.Struct("!BQQQ")

U64_MAX = (1 << 64) - 1


def ipc_err(error: IpcProtocolError) -> Err[IpcProtocolError]:
    """Create a consistently contextualized protocol error.

    Returns:
        Protocol error with stable namespace and context.
    """
    return Err(
        error=error,
        namespace="analysis_ipc_protocol",
        context_msg="Failed to process analysis IPC message",
    )


def encode_command(
    command: WorkerCommand,
) -> Result[bytes, IpcProtocolError]:
    """Encode a worker command into one fixed-size control header.

    Returns:
        Encoded header or a typed field-validation error.
    """
    if isinstance(command, AnalyzeBatch):
        transfer_id = int(command.transfer_id)
        sequence = int(command.sequence)
        payload_size = command.payload_size

        if not 0 <= transfer_id <= U64_MAX:
            return ipc_err(IpcProtocolError.INVALID_TRANSFER_ID)

        if not 0 <= sequence <= U64_MAX:
            return ipc_err(IpcProtocolError.INVALID_SEQUENCE)

        if not 0 < payload_size <= U64_MAX:
            return ipc_err(IpcProtocolError.INVALID_PAYLOAD_SIZE)

        return Ok(
            HEADER.pack(
                MessageTag.ANALYZE_BATCH,
                transfer_id,
                sequence,
                payload_size,
            )
        )

    # WorkerCommand is AnalyzeBatch | StopWorker
    # AnalyzeBatch was handled above, command is narrowed to StopWorker
    return Ok(
        HEADER.pack(
            MessageTag.STOP_WORKER,
            0,
            0,
            0,
        )
    )


def decode_command(
    payload: bytes,
) -> Result[WorkerCommand, IpcProtocolError]:
    """Decode and validate one fixed-size worker-command header.

    Returns:
        Typed worker command or a protocol error.
    """
    if len(payload) != HEADER.size:
        return ipc_err(IpcProtocolError.MALFORMED_MESSAGE)

    try:
        tag_raw, value1, value2, value3 = HEADER.unpack(payload)
    except struct.error:
        return ipc_err(IpcProtocolError.MALFORMED_MESSAGE)

    try:
        tag = MessageTag(tag_raw)
    except ValueError:
        return ipc_err(IpcProtocolError.UNKNOWN_MESSAGE)

    if tag == MessageTag.ANALYZE_BATCH:
        if value3 == 0:
            return ipc_err(IpcProtocolError.INVALID_PAYLOAD_SIZE)
        return Ok(
            AnalyzeBatch(
                transfer_id=TransferId(value1),
                sequence=Sequence(value2),
                payload_size=value3,
            )
        )

    if tag == MessageTag.STOP_WORKER:
        if value1 != 0 or value2 != 0 or value3 != 0:
            return ipc_err(IpcProtocolError.MALFORMED_MESSAGE)

        return Ok(StopWorker())

    return ipc_err(IpcProtocolError.UNKNOWN_MESSAGE)
