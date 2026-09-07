"""Drive one cooperative generator task by a single operation."""

from dataclasses import dataclass
from enum import Enum
from typing import NewType

from typed_errs import Err, Ok, Option, Result

from pacman.analyze.events import AnalysisEvent
from pacman.analyze.runtime.operations import AnalyzerCoroutine, Operation

TaskId = NewType("TaskId", int)


class TaskError(Enum):
    """Failures encountered while stepping an analyzer task."""

    ANALYZER_FAILED = "analyzer_failed"
    INVALID_OPERATION = "invalid_operation"


@dataclass(frozen=True, slots=True)
class TaskCompleted:
    """Marker returned when a generator exits normally."""


@dataclass(slots=True)
class Task:
    """Native coroutine plus the state required to resume it correctly."""

    id: TaskId
    coroutine: AnalyzerCoroutine
    started: bool = False

    def step(
        self,
        value: Option[AnalysisEvent],
    ) -> Result[Operation | TaskCompleted, TaskError]:
        """Advance the generator through exactly one yielded operation.

        Returns:
            Its next operation, completion, or a controlled task failure.
        """
        try:
            if not self.started:
                yielded = self.coroutine.send(None)
                self.started = True
            else:
                yielded = self.coroutine.send(value)
        except StopIteration:
            return Ok(TaskCompleted())
        except Exception:
            return Err(
                error=TaskError.ANALYZER_FAILED,
                namespace="analysis_task",
                context_msg=f"Analysis task {int(self.id)} failed",
            )

        if not isinstance(yielded, Operation):
            return Err(
                error=TaskError.INVALID_OPERATION,
                namespace="analysis_task",
                context_msg=f"Analysis task {int(self.id)} yielded an invalid operation",
            )
        return Ok(yielded)
