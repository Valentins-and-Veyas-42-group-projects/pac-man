import pytest
from pacman.analyze.runtime.ipc_protocol import (
    HEADER,
    U64_MAX,
    AnalyzeBatch,
    IpcProtocolError,
    MessageTag,
    Sequence,
    StopWorker,
    TransferId,
    decode_command,
    encode_command,
)
from typed_errs import Err


@pytest.mark.parametrize(
    "command",
    [
        AnalyzeBatch(TransferId(7), Sequence(42), 4096),
        StopWorker(),
    ],
)
def test_command_round_trip(command: AnalyzeBatch | StopWorker) -> None:
    encoded = encode_command(command).unwrap()

    assert len(encoded) == HEADER.size
    assert decode_command(encoded).unwrap() == command


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (
            AnalyzeBatch(TransferId(-1), Sequence(0), 1),
            IpcProtocolError.INVALID_TRANSFER_ID,
        ),
        (
            AnalyzeBatch(TransferId(U64_MAX + 1), Sequence(0), 1),
            IpcProtocolError.INVALID_TRANSFER_ID,
        ),
        (
            AnalyzeBatch(TransferId(0), Sequence(-1), 1),
            IpcProtocolError.INVALID_SEQUENCE,
        ),
        (
            AnalyzeBatch(TransferId(0), Sequence(U64_MAX + 1), 1),
            IpcProtocolError.INVALID_SEQUENCE,
        ),
        (
            AnalyzeBatch(TransferId(0), Sequence(0), 0),
            IpcProtocolError.INVALID_PAYLOAD_SIZE,
        ),
        (
            AnalyzeBatch(TransferId(0), Sequence(0), U64_MAX + 1),
            IpcProtocolError.INVALID_PAYLOAD_SIZE,
        ),
    ],
)
def test_encode_rejects_out_of_range_fields(
    command: AnalyzeBatch,
    expected: IpcProtocolError,
) -> None:
    result = encode_command(command)

    assert isinstance(result, Err)
    assert result.error is expected


@pytest.mark.parametrize("payload", [b"", bytes(HEADER.size - 1), bytes(HEADER.size + 1)])
def test_decode_rejects_incorrect_header_size(payload: bytes) -> None:
    result = decode_command(payload)

    assert isinstance(result, Err)
    assert result.error is IpcProtocolError.MALFORMED_MESSAGE


def test_decode_rejects_unknown_tag() -> None:
    result = decode_command(HEADER.pack(255, 0, 0, 0))

    assert isinstance(result, Err)
    assert result.error is IpcProtocolError.UNKNOWN_MESSAGE


def test_decode_rejects_output_tag_as_command() -> None:
    result = decode_command(HEADER.pack(MessageTag.BATCH_RELEASED, 1, 2, 0))

    assert isinstance(result, Err)
    assert result.error is IpcProtocolError.UNKNOWN_MESSAGE


def test_decode_rejects_stop_command_with_reserved_data() -> None:
    result = decode_command(HEADER.pack(MessageTag.STOP_WORKER, 1, 0, 0))

    assert isinstance(result, Err)
    assert result.error is IpcProtocolError.MALFORMED_MESSAGE


def test_decode_rejects_zero_sized_batch() -> None:
    result = decode_command(HEADER.pack(MessageTag.ANALYZE_BATCH, 1, 2, 0))

    assert isinstance(result, Err)
    assert result.error is IpcProtocolError.INVALID_PAYLOAD_SIZE
