"""Platform-independent lifecycle contract for replay analysis workers."""

from enum import Enum
from typing import Protocol

from typed_errs import Err, Result

from pacman.analyze.messages import AnalysisMessage
from pacman.replay.models import FrameBatch


class WorkerStatus(Enum):
    """Lifecycle states of an analysis worker."""

    CREATED = "created"
    RUNNING = "running"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


class AnalysisOffer(Enum):
    """Immediate outcome of offering a replay batch."""

    ACCEPTED = "accepted"
    QUEUE_FULL = "queue_full"
    CLOSED = "closed"
    WORKER_DEAD = "worker_dead"
    BATCH_FAILED = "batch_failed"


class AnalysisWorkerError(Enum):
    """Failures while managing an analysis worker."""

    INVALID_QUEUE_CAPACITY = "invalid_queue_capacity"
    INVALID_STATE = "invalid_state"
    CREATE_FAILED = "create_failed"
    START_FAILED = "start_failed"
    CLOSE_FAILED = "close_failed"
    BATCH_DECODE_FAILED = "batch_decode_failed"
    IPC_FAILED = "ipc_failed"
    INVALID_ACKNOWLEDGEMENT = "invalid_acknowledgement"


def worker_err(error: AnalysisWorkerError) -> Err[AnalysisWorkerError]:
    """Return a contextual worker error."""
    return Err(
        error=error,
        namespace="analysis_worker",
        context_msg="Failed to manage analysis worker",
    )


class AnalysisWorkerLike(Protocol):
    """The lifecycle used by the replay pipeline, independent of transport."""

    status: WorkerStatus

    def start(self) -> Result[None, AnalysisWorkerError]:
        """Begin accepting replay batches."""
        ...

    def offer(self, batch: FrameBatch) -> AnalysisOffer:
        """Offer one batch without imposing transport details on the caller."""
        ...

    def drain(self) -> tuple[AnalysisMessage, ...]:
        """Return messages produced since the previous drain."""
        ...

    def close(self) -> Result[None, AnalysisWorkerError]:
        """Stop the worker and release its resources."""
        ...
