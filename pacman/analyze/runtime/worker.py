"""Process lifetime and message transport for replay analysis."""

import multiprocessing
from dataclasses import dataclass
from enum import Enum
from multiprocessing.process import BaseProcess
from multiprocessing.queues import Queue
from queue import Empty, Full
from typing import TypeAlias

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.messages import AnalysisMessage
from pacman.analyze.runtime.runtime import AnalysisRuntime, AnalysisRuntimeError
from pacman.analyze.simulation import SimulationRules
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


class AnalysisWorkerError(Enum):
    """Failures while managing the analysis process lifetime."""

    INVALID_QUEUE_CAPACITY = "invalid_queue_capacity"
    INVALID_STATE = "invalid_state"
    CREATE_FAILED = "create_failed"
    START_FAILED = "start_failed"
    CLOSE_FAILED = "close_failed"


@dataclass(frozen=True, slots=True)
class ConsumeBatch:
    """Ask the child runtime to consume one replay batch."""

    batch: FrameBatch


@dataclass(frozen=True, slots=True)
class StopWorker:
    """Ask the child process to finish queued work and exit."""


WorkerCommand: TypeAlias = ConsumeBatch | StopWorker


@dataclass(frozen=True, slots=True)
class RuntimeFailed:
    """Report a typed runtime failure to the parent process."""

    error: AnalysisRuntimeError


WorkerOutput: TypeAlias = AnalysisMessage | RuntimeFailed


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


def run_analysis_worker(
    maze: Maze,
    rules: SimulationRules,
    input_queue: Queue[WorkerCommand],
    output_queue: Queue[WorkerOutput],
) -> None:
    """Own and drive one analysis runtime inside the child process."""
    runtime = AnalysisRuntime.create(maze, rules)
    if isinstance(runtime, Err):
        output_queue.put(RuntimeFailed(runtime.error))
        return

    while True:
        try:
            command = input_queue.get()
        except (EOFError, OSError):
            return

        if isinstance(command, StopWorker):
            return

        consumed = runtime.value.consume(command.batch)
        if isinstance(consumed, Err):
            output_queue.put(RuntimeFailed(consumed.error))
            return

        for message in consumed.value:
            output_queue.put(message)


@dataclass(slots=True)
class AnalysisWorker:
    """Own a bounded IPC queue and one replay-analysis process."""

    status: WorkerStatus
    input_queue: Queue[WorkerCommand]
    output_queue: Queue[WorkerOutput]
    process: BaseProcess
    pending_messages: list[AnalysisMessage]
    failure: Option[AnalysisRuntimeError]

    @classmethod
    def create(
        cls,
        maze: Maze,
        rules: SimulationRules,
        queue_capacity: int = 32,
    ) -> Result["AnalysisWorker", AnalysisWorkerError]:
        """Allocate queues and an unstarted child process.

        Returns:
            Created worker or a typed allocation error.
        """
        if queue_capacity <= 0:
            return worker_err(AnalysisWorkerError.INVALID_QUEUE_CAPACITY)

        try:
            context = multiprocessing.get_context("spawn")
            input_queue: Queue[WorkerCommand] = context.Queue(queue_capacity)
            output_queue: Queue[WorkerOutput] = context.Queue()
            process = context.Process(
                target=run_analysis_worker,
                args=(maze, rules, input_queue, output_queue),
                name="pacman-analysis",
            )
        except Exception:
            return worker_err(AnalysisWorkerError.CREATE_FAILED)

        return Ok(
            cls(
                status=WorkerStatus.CREATED,
                input_queue=input_queue,
                output_queue=output_queue,
                process=process,
                pending_messages=[],
                failure=Nothing(),
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
        self.status = WorkerStatus.RUNNING
        return Ok(None)

    def offer(self, batch: FrameBatch) -> AnalysisOffer:
        """Offer a batch without ever waiting for queue capacity.

        Returns:
            Immediate backpressure or lifecycle outcome.
        """
        if self.status in (WorkerStatus.CLOSING, WorkerStatus.CLOSED):
            return AnalysisOffer.CLOSED
        if self.status is not WorkerStatus.RUNNING or not self.process.is_alive():
            self.status = WorkerStatus.FAILED
            return AnalysisOffer.WORKER_DEAD
        try:
            self.input_queue.put_nowait(ConsumeBatch(batch))
        except Full:
            return AnalysisOffer.QUEUE_FULL
        except (OSError, ValueError):
            self.status = WorkerStatus.FAILED
            return AnalysisOffer.WORKER_DEAD
        return AnalysisOffer.ACCEPTED

    def drain(self) -> tuple[AnalysisMessage, ...]:
        """Collect every currently available child-process message.

        Returns:
            Messages received since the previous drain.
        """
        if self.status is not WorkerStatus.CLOSED:
            self._receive_outputs()
        messages = tuple(self.pending_messages)
        self.pending_messages.clear()
        return messages

    def close(self, timeout_seconds: float = 5.0) -> Result[None, AnalysisWorkerError]:
        """Finish queued work, stop the child, and release IPC resources.

        Returns:
            Success, including repeated close, or a typed shutdown error.
        """
        if self.status is WorkerStatus.CLOSED:
            return Ok(None)
        if self.status is WorkerStatus.CREATED:
            self.status = WorkerStatus.CLOSED
            return self._close_queues()
        if self.status not in (WorkerStatus.RUNNING, WorkerStatus.FAILED):
            return worker_err(AnalysisWorkerError.INVALID_STATE)

        self.status = WorkerStatus.CLOSING
        try:
            if self.process.is_alive():
                self.input_queue.put(StopWorker(), timeout=timeout_seconds)
                self.process.join(timeout_seconds)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout_seconds)
            self._receive_outputs()
            self.process.close()
        except (AssertionError, Full, OSError, ValueError):
            self.status = WorkerStatus.FAILED
            return worker_err(AnalysisWorkerError.CLOSE_FAILED)

        closed = self._close_queues()
        if isinstance(closed, Err):
            self.status = WorkerStatus.FAILED
            return closed
        self.status = WorkerStatus.CLOSED
        return Ok(None)

    def _receive_outputs(self) -> None:
        """Move available IPC outputs into parent-owned state."""
        while True:
            try:
                output = self.output_queue.get_nowait()
            except Empty:
                return
            except (OSError, ValueError):
                self.status = WorkerStatus.FAILED
                return

            if isinstance(output, RuntimeFailed):
                self.failure = Some(output.error)
                self.status = WorkerStatus.FAILED
            else:
                self.pending_messages.append(output)

    def _close_queues(self) -> Result[None, AnalysisWorkerError]:
        """Release multiprocessing queue feeder resources.

        Returns:
            Success or a typed queue-cleanup error.
        """
        try:
            self.input_queue.close()
            self.input_queue.join_thread()
            self.output_queue.close()
            self.output_queue.join_thread()
        except (OSError, ValueError):
            return worker_err(AnalysisWorkerError.CLOSE_FAILED)
        return Ok(None)
