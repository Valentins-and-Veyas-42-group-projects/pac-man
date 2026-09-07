"""Unix socket transport for analysis commands and file descriptors."""

import array
import os
import socket
from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some, catch_bubble

from pacman.analyze.runtime.ipc_protocol import (
    HEADER,
    AnalyzeBatch,
    StopWorker,
    WorkerCommand,
    WorkerOutput,
    decode_command,
    decode_output,
    encode_command,
    encode_output,
)

FD_ITEM_SIZE = array.array("i").itemsize
ANCILLARY_SIZE = socket.CMSG_SPACE(FD_ITEM_SIZE)
MAX_OUTPUT_PACKET_SIZE = 1024 * 1024


class SocketTransportError(Enum):
    """Failures while transporting commands over a Unix socket."""

    CREATE_FAILED = "create_failed"
    ENCODE_FAILED = "encode_failed"
    SEND_FAILED = "send_failed"
    RECEIVE_FAILED = "receive_failed"
    PROTOCOL_FAILED = "protocol_failed"
    TRUNCATED_MESSAGE = "truncated_message"
    MISSING_DESCRIPTOR = "missing_descriptor"
    UNEXPECTED_DESCRIPTOR = "unexpected_descriptor"
    TOO_MANY_DESCRIPTORS = "too_many_descriptors"


def socket_transport_err(error: SocketTransportError) -> Err[SocketTransportError]:
    """Create a consistently contextualized socket-transport error.

    Returns:
        Socket transport error with stable namespace and context.
    """
    return Err(
        error=error,
        namespace="analysis_socket_transport",
        context_msg="Failed to transport analysis IPC command",
    )


@dataclass(frozen=True, slots=True)
class ReceivedCommand:
    """Decoded command and descriptor whose ownership moved to the receiver."""

    command: WorkerCommand
    descriptor: Option[int]


def create_socket_pair() -> Result[tuple[socket.socket, socket.socket], SocketTransportError]:
    """Create a connected local sequenced-packet socket pair.

    Returns:
        Parent and child endpoints or a typed creation error.
    """
    try:
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    except OSError:
        return socket_transport_err(SocketTransportError.CREATE_FAILED)
    return Ok((parent, child))


@catch_bubble
def send_command(
    connection: socket.socket,
    command: WorkerCommand,
    descriptor: Option[int],
) -> Result[None, SocketTransportError]:
    """Send one command with its required optional file descriptor.

    Returns:
        Success or a typed command-validation/transport error.
    """
    if isinstance(command, AnalyzeBatch) and isinstance(descriptor, Nothing):
        return socket_transport_err(SocketTransportError.MISSING_DESCRIPTOR)
    if isinstance(command, StopWorker) and isinstance(descriptor, Some):
        return socket_transport_err(SocketTransportError.UNEXPECTED_DESCRIPTOR)

    encoded: bytes = (
        encode_command(command).map_err_with(lambda _error: socket_transport_err(SocketTransportError.ENCODE_FAILED)).q
    )

    ancillary: list[tuple[int, int, bytes]] = []
    if isinstance(descriptor, Some):
        descriptors = array.array("i", [descriptor.value])
        ancillary.append((
            socket.SOL_SOCKET,
            socket.SCM_RIGHTS,
            descriptors.tobytes(),
        ))

    try:
        sent = connection.sendmsg([encoded], ancillary)
    except (OSError, ValueError):
        return socket_transport_err(SocketTransportError.SEND_FAILED)
    if sent != len(encoded):
        return socket_transport_err(SocketTransportError.SEND_FAILED)
    return Ok(None)


def receive_command(
    connection: socket.socket,
) -> Result[ReceivedCommand, SocketTransportError]:
    """Receive one command and take ownership of its passed descriptor.

    Returns:
        Validated command/descriptor pair or a typed transport error.
    """
    try:
        payload, ancillary, flags, _ = connection.recvmsg(HEADER.size, ANCILLARY_SIZE)
    except (OSError, ValueError):
        return socket_transport_err(SocketTransportError.RECEIVE_FAILED)

    descriptors = _extract_descriptors(ancillary)
    if isinstance(descriptors, Err):
        return descriptors

    received_fds = descriptors.value
    if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or len(payload) != HEADER.size:
        _close_descriptors(received_fds)
        return socket_transport_err(SocketTransportError.TRUNCATED_MESSAGE)

    decoded = decode_command(payload)
    if isinstance(decoded, Err):
        _close_descriptors(received_fds)
        return socket_transport_err(SocketTransportError.PROTOCOL_FAILED)

    if len(received_fds) > 1:
        _close_descriptors(received_fds)
        return socket_transport_err(SocketTransportError.TOO_MANY_DESCRIPTORS)

    if isinstance(decoded.value, AnalyzeBatch):
        if not received_fds:
            return socket_transport_err(SocketTransportError.MISSING_DESCRIPTOR)
        return Ok(ReceivedCommand(decoded.value, Some(received_fds[0])))

    if received_fds:
        _close_descriptors(received_fds)
        return socket_transport_err(SocketTransportError.UNEXPECTED_DESCRIPTOR)
    return Ok(ReceivedCommand(decoded.value, Nothing()))


@catch_bubble
def send_output(
    connection: socket.socket,
    output: WorkerOutput,
) -> Result[None, SocketTransportError]:
    """Send one analysis output without ancillary descriptors.

    Returns:
        Success or a typed encoding/transport error.
    """
    encoded: bytes = (
        encode_output(output).map_err_with(lambda _error: socket_transport_err(SocketTransportError.ENCODE_FAILED)).q
    )
    try:
        sent = connection.send(encoded)
    except (OSError, ValueError):
        return socket_transport_err(SocketTransportError.SEND_FAILED)
    if sent != len(encoded):
        return socket_transport_err(SocketTransportError.SEND_FAILED)
    return Ok(None)


@catch_bubble
def receive_output(
    connection: socket.socket,
) -> Result[WorkerOutput, SocketTransportError]:
    """Receive and decode one complete analysis-output packet.

    Returns:
        Typed worker output or a transport/protocol error.
    """
    try:
        payload, _, flags, _ = connection.recvmsg(MAX_OUTPUT_PACKET_SIZE)
    except (OSError, ValueError):
        return socket_transport_err(SocketTransportError.RECEIVE_FAILED)
    if flags & socket.MSG_TRUNC:
        return socket_transport_err(SocketTransportError.TRUNCATED_MESSAGE)

    output: WorkerOutput = (
        decode_output(payload).map_err_with(lambda _error: socket_transport_err(SocketTransportError.PROTOCOL_FAILED)).q
    )
    return Ok(output)


def _extract_descriptors(
    ancillary: list[tuple[int, int, bytes]],
) -> Result[tuple[int, ...], SocketTransportError]:
    """Decode received ``SCM_RIGHTS`` records.

    Returns:
        Owned descriptors or a typed ancillary-data error.
    """
    descriptors: list[int] = []
    for level, kind, data in ancillary:
        if level != socket.SOL_SOCKET or kind != socket.SCM_RIGHTS:
            _close_descriptors(tuple(descriptors))
            return socket_transport_err(SocketTransportError.RECEIVE_FAILED)
        if len(data) % FD_ITEM_SIZE != 0:
            _close_descriptors(tuple(descriptors))
            return socket_transport_err(SocketTransportError.RECEIVE_FAILED)

        values = array.array("i")
        try:
            values.frombytes(data)
        except ValueError:
            _close_descriptors(tuple(descriptors))
            return socket_transport_err(SocketTransportError.RECEIVE_FAILED)
        descriptors.extend(values)
    return Ok(tuple(descriptors))


def _close_descriptors(descriptors: tuple[int, ...]) -> None:
    """Close descriptors rejected before ownership could reach a caller."""
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError:
            pass
