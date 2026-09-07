import mmap
import os

from pacman.analyze.messages import TurnObserved
from pacman.analyze.runtime.ipc_protocol import (
    AnalysisProduced,
    AnalyzeBatch,
    Sequence,
    StopWorker,
    TransferId,
)
from pacman.analyze.runtime.shared_batch import SharedBatch
from pacman.analyze.runtime.socket_transport import (
    SocketTransportError,
    create_socket_pair,
    receive_command,
    receive_output,
    send_command,
    send_output,
)
from pacman.replay.batch_codec import decode_batch_from
from pacman.replay.models import (
    Coord,
    Direction,
    Frame,
    FrameBatch,
    GamePhase,
    PlayerFrame,
    Position,
    ReplayId,
    Score,
    Tick,
)
from typed_errs import Err, Nothing, Some


def batch() -> FrameBatch:
    return FrameBatch(
        ReplayId(3),
        (
            Frame(
                Tick(14),
                PlayerFrame(Position(Coord(5), Coord(7)), Direction.LEFT),
                (),
                Score(240),
                2,
                GamePhase.PLAYING,
            ),
        ),
        (),
    )


def test_descriptor_exposes_shared_batch_to_receiver() -> None:
    original = batch()
    shared = SharedBatch.create(TransferId(8), Sequence(12), original).unwrap()
    shared.seal().unwrap()
    parent, child = create_socket_pair().unwrap()
    received_fd = -1

    try:
        command = AnalyzeBatch(shared.transfer_id, shared.sequence, shared.payload_size)
        send_command(parent, command, Some(shared.fd)).unwrap()
        received = receive_command(child).unwrap()
        received_fd = received.descriptor.unwrap()

        shared.close().unwrap()
        received_mapping = mmap.mmap(
            received_fd,
            command.payload_size,
            access=mmap.ACCESS_READ,
        )
        try:
            view = memoryview(received_mapping)
            try:
                decoded = decode_batch_from(view).unwrap()
            finally:
                view.release()
        finally:
            received_mapping.close()

        assert received.command == command
        assert decoded == original
    finally:
        if received_fd >= 0:
            os.close(received_fd)
        if shared.status.value != "closed":
            shared.close().unwrap()
        parent.close()
        child.close()


def test_stop_command_round_trips_without_descriptor() -> None:
    parent, child = create_socket_pair().unwrap()
    try:
        send_command(parent, StopWorker(), Nothing()).unwrap()

        received = receive_command(child).unwrap()

        assert received.command == StopWorker()
        assert isinstance(received.descriptor, Nothing)
    finally:
        parent.close()
        child.close()


def test_analyze_batch_requires_descriptor_before_sending() -> None:
    parent, child = create_socket_pair().unwrap()
    try:
        result = send_command(
            parent,
            AnalyzeBatch(TransferId(1), Sequence(2), 64),
            Nothing(),
        )

        assert isinstance(result, Err)
        assert result.error is SocketTransportError.MISSING_DESCRIPTOR
    finally:
        parent.close()
        child.close()


def test_stop_command_rejects_descriptor_before_sending() -> None:
    read_fd, write_fd = os.pipe()
    parent, child = create_socket_pair().unwrap()
    try:
        result = send_command(parent, StopWorker(), Some(read_fd))

        assert isinstance(result, Err)
        assert result.error is SocketTransportError.UNEXPECTED_DESCRIPTOR
    finally:
        os.close(read_fd)
        os.close(write_fd)
        parent.close()
        child.close()


def test_receive_rejects_truncated_control_message() -> None:
    parent, child = create_socket_pair().unwrap()
    try:
        parent.send(b"short")

        result = receive_command(child)

        assert isinstance(result, Err)
        assert result.error is SocketTransportError.TRUNCATED_MESSAGE
    finally:
        parent.close()
        child.close()


def test_analysis_output_round_trips_over_socket() -> None:
    parent, child = create_socket_pair().unwrap()
    output = AnalysisProduced(
        Sequence(7),
        (TurnObserved(ReplayId(3), Tick(14)),),
    )
    try:
        send_output(child, output).unwrap()

        assert receive_output(parent).unwrap() == output
    finally:
        parent.close()
        child.close()
