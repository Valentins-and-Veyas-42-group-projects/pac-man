"""Pure-Python, in-process replay analysis worker."""

from dataclasses import dataclass, field

from typed_errs import Err, Ok, Result

from pacman.analyze.messages import AnalysisMessage
from pacman.analyze.runtime.runtime import AnalysisRuntime
from pacman.analyze.runtime.worker_contract import (
    AnalysisOffer,
    AnalysisWorkerError,
    WorkerStatus,
    worker_err,
)
from pacman.analyze.simulation import SimulationRules
from pacman.replay.models import FrameBatch, Maze


@dataclass(slots=True)
class InlineAnalysisWorker:
    """Run the reference analysis in the caller when isolation is unavailable."""

    runtime: AnalysisRuntime
    status: WorkerStatus = WorkerStatus.CREATED
    pending_messages: list[AnalysisMessage] = field(default_factory=list)

    @classmethod
    def create(
        cls, maze: Maze, rules: SimulationRules, queue_capacity: int = 32
    ) -> Result["InlineAnalysisWorker", AnalysisWorkerError]:
        """Build a reference runtime with the same worker lifecycle.

        Returns:
            A worker or a typed construction error.
        """
        if queue_capacity <= 0:
            return worker_err(AnalysisWorkerError.INVALID_QUEUE_CAPACITY)
        runtime = AnalysisRuntime.create(maze, rules)
        if isinstance(runtime, Err):
            return worker_err(AnalysisWorkerError.CREATE_FAILED)
        return Ok(cls(runtime.value))

    def start(self) -> Result[None, AnalysisWorkerError]:
        """Enter the running state without creating a process.

        Returns:
            Success or a lifecycle error.
        """
        if self.status is not WorkerStatus.CREATED:
            return worker_err(AnalysisWorkerError.INVALID_STATE)
        self.status = WorkerStatus.RUNNING
        return Ok(None)

    def offer(self, batch: FrameBatch) -> AnalysisOffer:
        """Consume a batch synchronously and buffer its analysis messages.

        Returns:
            The immediate offer outcome.
        """
        if self.status in (WorkerStatus.CLOSING, WorkerStatus.CLOSED):
            return AnalysisOffer.CLOSED
        if self.status is not WorkerStatus.RUNNING:
            return AnalysisOffer.WORKER_DEAD
        result = self.runtime.consume(batch)
        if isinstance(result, Err):
            self.status = WorkerStatus.FAILED
            return AnalysisOffer.WORKER_DEAD
        self.pending_messages.extend(result.value)
        return AnalysisOffer.ACCEPTED

    def drain(self) -> tuple[AnalysisMessage, ...]:
        """Return and clear messages produced by accepted batches."""
        messages = tuple(self.pending_messages)
        self.pending_messages.clear()
        return messages

    def close(self) -> Result[None, AnalysisWorkerError]:
        """Close the logical worker, preserving messages until drained.

        Returns:
            Success, including repeated close.
        """
        self.status = WorkerStatus.CLOSED
        return Ok(None)
