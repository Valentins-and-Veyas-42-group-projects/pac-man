"""Typed binary control protocol for analysis IPC."""

import struct
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import NewType, TypeAlias

from typed_errs import Err, Ok, Result, catch_bubble

from pacman.analyze.messages import (
    AnalysisMessage,
    DeathQueued,
    DecisionEvaluationQueued,
    TurnObserved,
)
from pacman.analyze.runtime.runtime import AnalysisRuntimeError
from pacman.replay.models import ReplayId, Tick

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
    INVALID_ANALYSIS_MESSAGE = "invalid_analysis_message"
    INVALID_RUNTIME_ERROR = "invalid_runtime_error"
    MALFORMED_MESSAGE = "malformed_message"


class MessageTag(IntEnum):
    """Stable numeric tags encoded into IPC headers."""

    ANALYZE_BATCH = 1
    STOP_WORKER = 2
    BATCH_RELEASED = 3
    ANALYSIS_PRODUCED = 4
    WORKER_FAILED = 5


class AnalysisMessageTag(IntEnum):
    """Stable tags for messages nested inside analysis output packets."""

    TURN_OBSERVED = 1
    DEATH_QUEUED = 2
    DECISION_EVALUATION_QUEUED = 3


class RuntimeErrorCode(IntEnum):
    """Stable wire codes for analysis runtime failures."""

    INVALID_STEP_BUDGET = 1
    GRAPH_FAILED = 2
    STATE_FAILED = 3
    WRONG_REPLAY = 4
    TICK_MOVED_BACKWARDS = 5
    LOOP_FAILED = 6
    STEP_BUDGET_EXHAUSTED = 7


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
ANALYSIS_MESSAGE = struct.Struct("!BQQQ")

U64_MAX = (1 << 64) - 1

RUNTIME_ERROR_CODES: dict[AnalysisRuntimeError, RuntimeErrorCode] = {
    AnalysisRuntimeError.INVALID_STEP_BUDGET: RuntimeErrorCode.INVALID_STEP_BUDGET,
    AnalysisRuntimeError.GRAPH_FAILED: RuntimeErrorCode.GRAPH_FAILED,
    AnalysisRuntimeError.STATE_FAILED: RuntimeErrorCode.STATE_FAILED,
    AnalysisRuntimeError.WRONG_REPLAY: RuntimeErrorCode.WRONG_REPLAY,
    AnalysisRuntimeError.TICK_MOVED_BACKWARDS: RuntimeErrorCode.TICK_MOVED_BACKWARDS,
    AnalysisRuntimeError.LOOP_FAILED: RuntimeErrorCode.LOOP_FAILED,
    AnalysisRuntimeError.STEP_BUDGET_EXHAUSTED: RuntimeErrorCode.STEP_BUDGET_EXHAUSTED,
}
RUNTIME_ERRORS: dict[RuntimeErrorCode, AnalysisRuntimeError] = {
    code: error for error, code in RUNTIME_ERROR_CODES.items()
}


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


@catch_bubble
def encode_output(output: WorkerOutput) -> Result[bytes, IpcProtocolError]:
    """Encode one worker output into a sequenced-packet payload.

    Returns:
        Encoded output packet or a typed field-validation error.
    """
    if isinstance(output, BatchReleased):
        transfer_id = int(output.transfer_id)
        sequence = int(output.sequence)
        if not 0 <= transfer_id <= U64_MAX:
            return ipc_err(IpcProtocolError.INVALID_TRANSFER_ID)
        if not 0 <= sequence <= U64_MAX:
            return ipc_err(IpcProtocolError.INVALID_SEQUENCE)
        return Ok(HEADER.pack(MessageTag.BATCH_RELEASED, transfer_id, sequence, 0))

    if isinstance(output, WorkerFailed):
        if output.error not in RUNTIME_ERROR_CODES:
            return ipc_err(IpcProtocolError.INVALID_RUNTIME_ERROR)
        code = RUNTIME_ERROR_CODES[output.error]
        return Ok(HEADER.pack(MessageTag.WORKER_FAILED, code, 0, 0))

    sequence = int(output.sequence)
    if not 0 <= sequence <= U64_MAX:
        return ipc_err(IpcProtocolError.INVALID_SEQUENCE)
    if len(output.messages) > U64_MAX:
        return ipc_err(IpcProtocolError.INVALID_PAYLOAD_SIZE)

    records: list[bytes] = []
    for message in output.messages:
        records.append(_encode_analysis_message(message).q)

    payload_size = len(records) * ANALYSIS_MESSAGE.size
    header = HEADER.pack(
        MessageTag.ANALYSIS_PRODUCED,
        sequence,
        len(records),
        payload_size,
    )
    return Ok(header + b"".join(records))


def decode_output(payload: bytes) -> Result[WorkerOutput, IpcProtocolError]:
    """Decode and validate one complete worker-output packet.

    Returns:
        Typed worker output or a protocol error.
    """
    if len(payload) < HEADER.size:
        return ipc_err(IpcProtocolError.MALFORMED_MESSAGE)
    try:
        tag_raw, value1, value2, value3 = HEADER.unpack_from(payload)
        tag = MessageTag(tag_raw)
    except (struct.error, ValueError):
        return ipc_err(IpcProtocolError.UNKNOWN_MESSAGE)

    if tag is MessageTag.BATCH_RELEASED:
        if len(payload) != HEADER.size or value3 != 0:
            return ipc_err(IpcProtocolError.MALFORMED_MESSAGE)
        return Ok(BatchReleased(TransferId(value1), Sequence(value2)))

    if tag is MessageTag.WORKER_FAILED:
        if len(payload) != HEADER.size or value2 != 0 or value3 != 0:
            return ipc_err(IpcProtocolError.MALFORMED_MESSAGE)
        try:
            code = RuntimeErrorCode(value1)
        except ValueError:
            return ipc_err(IpcProtocolError.INVALID_RUNTIME_ERROR)
        if code not in RUNTIME_ERRORS:
            return ipc_err(IpcProtocolError.INVALID_RUNTIME_ERROR)
        return Ok(WorkerFailed(RUNTIME_ERRORS[code]))

    if tag is not MessageTag.ANALYSIS_PRODUCED:
        return ipc_err(IpcProtocolError.UNKNOWN_MESSAGE)

    expected_size = value2 * ANALYSIS_MESSAGE.size
    if value3 != expected_size or len(payload) != HEADER.size + expected_size:
        return ipc_err(IpcProtocolError.MALFORMED_MESSAGE)

    messages: list[AnalysisMessage] = []
    offset = HEADER.size
    for _ in range(value2):
        decoded = _decode_analysis_message(payload, offset)
        if isinstance(decoded, Err):
            return decoded
        messages.append(decoded.value)
        offset += ANALYSIS_MESSAGE.size
    return Ok(AnalysisProduced(Sequence(value1), tuple(messages)))


def _encode_analysis_message(
    message: AnalysisMessage,
) -> Result[bytes, IpcProtocolError]:
    """Encode one fixed-size nested analysis message.

    Returns:
        Encoded message record or a typed value error.
    """
    if isinstance(message, TurnObserved):
        values = (AnalysisMessageTag.TURN_OBSERVED, int(message.replay_id), int(message.tick), 0)
    elif isinstance(message, DeathQueued):
        values = (AnalysisMessageTag.DEATH_QUEUED, int(message.replay_id), int(message.tick), 0)
    else:
        values = (
            AnalysisMessageTag.DECISION_EVALUATION_QUEUED,
            int(message.replay_id),
            int(message.decision_tick),
            int(message.evaluation_tick),
        )
    if any(not 0 <= int(value) <= U64_MAX for value in values[1:]):
        return ipc_err(IpcProtocolError.INVALID_ANALYSIS_MESSAGE)
    return Ok(ANALYSIS_MESSAGE.pack(*values))


def _decode_analysis_message(
    payload: bytes,
    offset: int,
) -> Result[AnalysisMessage, IpcProtocolError]:
    """Decode one nested analysis message at a validated offset.

    Returns:
        Typed analysis message or a protocol error.
    """
    try:
        tag_raw, value1, value2, value3 = ANALYSIS_MESSAGE.unpack_from(payload, offset)
        tag = AnalysisMessageTag(tag_raw)
    except (struct.error, ValueError):
        return ipc_err(IpcProtocolError.INVALID_ANALYSIS_MESSAGE)

    if tag is AnalysisMessageTag.TURN_OBSERVED:
        if value3 != 0:
            return ipc_err(IpcProtocolError.INVALID_ANALYSIS_MESSAGE)
        return Ok(TurnObserved(ReplayId(value1), Tick(value2)))
    if tag is AnalysisMessageTag.DEATH_QUEUED:
        if value3 != 0:
            return ipc_err(IpcProtocolError.INVALID_ANALYSIS_MESSAGE)
        return Ok(DeathQueued(ReplayId(value1), Tick(value2)))
    return Ok(
        DecisionEvaluationQueued(
            ReplayId(value1),
            Tick(value2),
            Tick(value3),
        )
    )
