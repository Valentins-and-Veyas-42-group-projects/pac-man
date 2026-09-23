"""Select a replay analysis worker without importing native IPC on browser runtimes."""

from enum import Enum

from typed_errs import Err, Ok, Result

from pacman.analyze.runtime.worker_contract import AnalysisWorkerError, AnalysisWorkerLike
from pacman.analyze.simulation import SimulationRules
from pacman.replay.models import Maze


class WorkerBackend(Enum):
    """Available Python replay-analysis execution modes."""

    PROCESS = "process"
    INLINE = "inline"


def create_analysis_worker(
    maze: Maze,
    rules: SimulationRules,
    queue_capacity: int = 32,
    backend: WorkerBackend = WorkerBackend.PROCESS,
) -> Result[AnalysisWorkerLike, AnalysisWorkerError]:
    """Create the selected platform worker with a shared lifecycle.

    Returns:
        A worker or a typed construction error.
    """
    if backend is WorkerBackend.INLINE:
        from pacman.analyze.runtime.inline_worker import InlineAnalysisWorker

        created = InlineAnalysisWorker.create(maze, rules, queue_capacity)
        if isinstance(created, Err):
            return created
        return Ok(created.value)

    from pacman.analyze.runtime.worker import AnalysisWorker

    created = AnalysisWorker.create(maze, rules, queue_capacity)
    if isinstance(created, Err):
        return created
    return Ok(created.value)
