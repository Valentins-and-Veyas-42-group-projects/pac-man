"""Process lifetime and mmap IPC orchestration for replay analysis."""

import mmap
import multiprocessing
import os
import socket
import time
from dataclasses import dataclass
from enum import Enum
from multiprocessing.process import BaseProcess

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.messages import AnalysisMessage
from pacman.analyze.runtime.ipc_protocol import (
    AnalysisProduced,
    AnalyzeBatch,
    BatchReleased,
    Sequence,
    StopWorker,
    TransferId,
    WorkerFailed,
)
from pacman.analyze.runtime.runtime import AnalysisRuntime, AnalysisRuntimeError
from pacman.analyze.runtime.shared_batch import SharedBatch
from pacman.analyze.runtime.socket_transport import (
    SocketTransportError,
    create_socket_pair,
    receive_command,
    receive_output,
    send_command,
    send_output,
)
from pacman.analyze.simulation import SimulationRules
from pacman.replay.batch_codec import decode_batch_from
from pacman.replay.models import FrameBatch, Maze


class WorkerStatus(Enum):
    """Lifecycle states of an analysis worker process."""

    CREATED = "created"
    RUNNING = "running"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


class AnalysisOffer(Enum):
    """Immediate outcome of offering work without blocking gameplay."""

    ACCEPTED = "accepted"
    QUEUE_FULL = "queue_full"
    CLOSED = "closed"
    WORKER_DEAD = "worker_dead"
    BATCH_FAILED = "batch_failed"


class AnalysisWorkerError(Enum):
    """Failures while managing the analysis process lifetime."""

    INVALID_QUEUE_CAPACITY = "invalid_queue_capacity"
    INVALID_STATE = "invalid_state"
    CREATE_FAILED = "create_failed"
    START_FAILED = "start_failed"
    CLOSE_FAILED = "close_failed"
    BATCH_DECODE_FAILED = "batch_decode_failed"
    IPC_FAILED = "ipc_failed"
    INVALID_ACKNOWLEDGEMENT = "invalid_acknowledgement"


def worker_err(error: AnalysisWorkerError) -> Err[AnalysisWorkerError]:
    """Create a consistently contextualized worker error.

    Returns:
        Worker error with stable namespace and context.
    """
    return Err(
        error=error,
        namespace="analysis_worker",
        context_msg="Failed to manage analysis worker",
    )


def decode_received_batch(
    descriptor: int,
    payload_size: int,
) -> Result[FrameBatch, AnalysisWorkerError]:
    """Map and decode a descriptor received by the child process.

    Returns:
        Decoded replay batch or a typed child-side error.
    """
    try:
        mapping = mmap.mmap(descriptor, payload_size, access=mmap.ACCESS_READ)
    except (OSError, ValueError):
        try:
            os.close(descriptor)
        except OSError:
            pass
        return worker_err(AnalysisWorkerError.BATCH_DECODE_FAILED)

    try:
        view = memoryview(mapping)
        try:
            decoded = decode_batch_from(view)
        finally:
            view.release()
    finally:
        mapping.close()
        try:
            os.close(descriptor)
        except OSError:
            pass

    if isinstance(decoded, Err):
        return worker_err(AnalysisWorkerError.BATCH_DECODE_FAILED)
    return Ok(decoded.value)


def run_analysis_worker(
    maze: Maze,
    rules: SimulationRules,
    connection: socket.socket,
) -> None:
    """Own and drive one analysis runtime inside the child process."""
    runtime = AnalysisRuntime.create(maze, rules)
    if isinstance(runtime, Err):
        _ = send_output(connection, WorkerFailed(runtime.error))
        connection.close()
        return

    while True:
        received = receive_command(connection)
        if isinstance(received, Err):
            connection.close()
            return

        command = received.value.command
        if isinstance(command, StopWorker):
            connection.close()
            return

        descriptor = received.value.descriptor
        if isinstance(descriptor, Nothing):
            connection.close()
            return

        batch = decode_received_batch(descriptor.value, command.payload_size)
        if isinstance(batch, Err):
            connection.close()
            return

        consumed = runtime.value.consume(batch.value)
        if isinstance(consumed, Err):
            _ = send_output(connection, WorkerFailed(consumed.error))
            _ = send_output(connection, BatchReleased(command.transfer_id, command.sequence))
            connection.close()
            return

        produced = send_output(
            connection,
            AnalysisProduced(command.sequence, consumed.value),
        )
        if isinstance(produced, Err):
            connection.close()
            return
        released = send_output(
            connection,
            BatchReleased(command.transfer_id, command.sequence),
        )
        if isinstance(released, Err):
            connection.close()
            return


@dataclass(slots=True)
class AnalysisWorker:
    """Own socket IPC, in-flight mmap batches, and one analysis process."""

    status: WorkerStatus
    connection: socket.socket
    child_connection: Option[socket.socket]
    process: BaseProcess
    max_in_flight_batches: int
    in_flight: dict[TransferId, SharedBatch]
    pending_messages: list[AnalysisMessage]
    failure: Option[AnalysisRuntimeError]
    next_transfer_id: int
    next_sequence: int

    @classmethod
    def create(
        cls,
        maze: Maze,
        rules: SimulationRules,
        queue_capacity: int = 32,
    ) -> Result["AnalysisWorker", AnalysisWorkerError]:
        """Allocate socket IPC and an unstarted child process.

        Returns:
            Created worker or a typed allocation error.
        """
        if queue_capacity <= 0:
            return worker_err(AnalysisWorkerError.INVALID_QUEUE_CAPACITY)

        pair = create_socket_pair()
        if isinstance(pair, Err):
            return worker_err(AnalysisWorkerError.CREATE_FAILED)
        parent, child = pair.value

        try:
            parent.setblocking(False)
            context = multiprocessing.get_context("spawn")
            process = context.Process(
                target=run_analysis_worker,
                args=(maze, rules, child),
                name="pacman-analysis",
            )
        except Exception:
            parent.close()
            child.close()
            return worker_err(AnalysisWorkerError.CREATE_FAILED)

        return Ok(
            cls(
                status=WorkerStatus.CREATED,
                connection=parent,
                child_connection=Some(child),
                process=process,
                max_in_flight_batches=queue_capacity,
                in_flight={},
                pending_messages=[],
                failure=Nothing(),
                next_transfer_id=0,
                next_sequence=0,
            )
        )

    def start(self) -> Result[None, AnalysisWorkerError]:
        """Start the child process exactly once.

        Returns:
            Success or a typed lifecycle error.
        """
        if self.status is not WorkerStatus.CREATED:
            return worker_err(AnalysisWorkerError.INVALID_STATE)
        try:
            self.process.start()
        except Exception:
            self.status = WorkerStatus.FAILED
            return worker_err(AnalysisWorkerError.START_FAILED)

        if isinstance(self.child_connection, Some):
            self.child_connection.value.close()
            self.child_connection = Nothing()
        self.status = WorkerStatus.RUNNING
        return Ok(None)

    def offer(self, batch: FrameBatch) -> AnalysisOffer:
        """Offer a shared batch without waiting for socket capacity.

        Returns:
            Immediate backpressure or lifecycle outcome.
        """
        if self.status in (WorkerStatus.CLOSING, WorkerStatus.CLOSED):
            return AnalysisOffer.CLOSED
        if self.status is not WorkerStatus.RUNNING or not self.process.is_alive():
            self.status = WorkerStatus.FAILED
            return AnalysisOffer.WORKER_DEAD

        _ = self._receive_outputs()
        if self.status is WorkerStatus.FAILED:
            return AnalysisOffer.WORKER_DEAD
        if len(self.in_flight) >= self.max_in_flight_batches:
            return AnalysisOffer.QUEUE_FULL

        transfer_id = TransferId(self.next_transfer_id)
        sequence = Sequence(self.next_sequence)
        shared = SharedBatch.create(transfer_id, sequence, batch)
        if isinstance(shared, Err):
            return AnalysisOffer.BATCH_FAILED
        sealed = shared.value.seal()
        if isinstance(sealed, Err):
            _ = shared.value.close()
            return AnalysisOffer.BATCH_FAILED

        command = AnalyzeBatch(transfer_id, sequence, shared.value.payload_size)
        sent = send_command(self.connection, command, Some(shared.value.fd))
        if isinstance(sent, Err):
            _ = shared.value.close()
            if sent.error is SocketTransportError.WOULD_BLOCK:
                return AnalysisOffer.QUEUE_FULL
            self.status = WorkerStatus.FAILED
            return AnalysisOffer.WORKER_DEAD

        self.in_flight[transfer_id] = shared.value
        self.next_transfer_id += 1
        self.next_sequence += 1
        return AnalysisOffer.ACCEPTED

    def drain(self) -> tuple[AnalysisMessage, ...]:
        """Collect every currently available child-process message.

        Returns:
            Messages received since the previous drain.
        """
        if self.status is not WorkerStatus.CLOSED:
            _ = self._receive_outputs()
        messages = tuple(self.pending_messages)
        self.pending_messages.clear()
        return messages

    def close(self, timeout_seconds: float = 5.0) -> Result[None, AnalysisWorkerError]:
        """Stop the child and release sockets and outstanding mappings.

        Returns:
            Success, including repeated close, or a typed shutdown error.
        """
        if self.status is WorkerStatus.CLOSED:
            return Ok(None)
        if timeout_seconds < 0:
            return worker_err(AnalysisWorkerError.CLOSE_FAILED)
        if self.status is WorkerStatus.CREATED:
            return self._close_created()
        if self.status not in (WorkerStatus.RUNNING, WorkerStatus.FAILED):
            return worker_err(AnalysisWorkerError.INVALID_STATE)

        self.status = WorkerStatus.CLOSING
        deadline = time.monotonic() + timeout_seconds
        if self.process.is_alive():
            sent = self._send_stop(timeout_seconds)
            if isinstance(sent, Err):
                self.status = WorkerStatus.FAILED

        while self.process.is_alive() and time.monotonic() < deadline:
            _ = self._receive_outputs()
            self.process.join(0.01)

        try:
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout_seconds)
            _ = self._receive_outputs()
            self.process.close()
        except (AssertionError, OSError, ValueError):
            self.status = WorkerStatus.FAILED
            return worker_err(AnalysisWorkerError.CLOSE_FAILED)

        cleaned = self._release_resources()
        if isinstance(cleaned, Err):
            self.status = WorkerStatus.FAILED
            return cleaned
        self.status = WorkerStatus.CLOSED
        return Ok(None)

    def _receive_outputs(self) -> Result[None, AnalysisWorkerError]:
        """Drain non-blocking output packets and release acknowledged mmap regions.

        Returns:
            Success or a typed transport/acknowledgement error.
        """
        while True:
            received = receive_output(self.connection)
            if isinstance(received, Err):
                if received.error is SocketTransportError.WOULD_BLOCK:
                    return Ok(None)
                if received.error is SocketTransportError.PEER_CLOSED:
                    if self.status is not WorkerStatus.CLOSING:
                        self.status = WorkerStatus.FAILED
                    return Ok(None)
                self.status = WorkerStatus.FAILED
                return worker_err(AnalysisWorkerError.IPC_FAILED)

            output = received.value
            if isinstance(output, AnalysisProduced):
                self.pending_messages.extend(output.messages)
            elif isinstance(output, WorkerFailed):
                self.failure = Some(output.error)
                self.status = WorkerStatus.FAILED
            else:
                released = self._release_batch(output)
                if isinstance(released, Err):
                    self.status = WorkerStatus.FAILED
                    return released

    def _release_batch(
        self,
        output: BatchReleased,
    ) -> Result[None, AnalysisWorkerError]:
        """Release one acknowledged parent-owned mapping.

        Returns:
            Success or a typed acknowledgement/cleanup error.
        """
        if output.transfer_id not in self.in_flight:
            return worker_err(AnalysisWorkerError.INVALID_ACKNOWLEDGEMENT)
        shared = self.in_flight.pop(output.transfer_id)
        if shared.sequence != output.sequence:
            _ = shared.close()
            return worker_err(AnalysisWorkerError.INVALID_ACKNOWLEDGEMENT)
        closed = shared.close()
        if isinstance(closed, Err):
            return worker_err(AnalysisWorkerError.CLOSE_FAILED)
        return Ok(None)

    def _send_stop(self, timeout_seconds: float) -> Result[None, AnalysisWorkerError]:
        """Send graceful shutdown with a bounded blocking timeout.

        Returns:
            Success or a typed socket error.
        """
        try:
            self.connection.settimeout(timeout_seconds)
            sent = send_command(self.connection, StopWorker(), Nothing())
            self.connection.setblocking(False)
        except (OSError, ValueError):
            return worker_err(AnalysisWorkerError.CLOSE_FAILED)
        if isinstance(sent, Err):
            return worker_err(AnalysisWorkerError.CLOSE_FAILED)
        return Ok(None)

    def _close_created(self) -> Result[None, AnalysisWorkerError]:
        """Close resources belonging to a process that never started.

        Returns:
            Success or a typed cleanup error.
        """
        try:
            self.connection.close()
            if isinstance(self.child_connection, Some):
                self.child_connection.value.close()
                self.child_connection = Nothing()
        except OSError:
            self.status = WorkerStatus.FAILED
            return worker_err(AnalysisWorkerError.CLOSE_FAILED)
        self.status = WorkerStatus.CLOSED
        return Ok(None)

    def _release_resources(self) -> Result[None, AnalysisWorkerError]:
        """Close the parent socket and every unacknowledged mapping.

        Returns:
            Success or a typed cleanup error.
        """
        failed = False
        for shared in self.in_flight.values():
            if isinstance(shared.close(), Err):
                failed = True
        self.in_flight.clear()
        try:
            self.connection.close()
        except OSError:
            failed = True
        if failed:
            return worker_err(AnalysisWorkerError.CLOSE_FAILED)
        return Ok(None)
