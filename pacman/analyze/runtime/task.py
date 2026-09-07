"""Drive one cooperative generator task by a single operation."""

from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum
from typing import NewType, TypeAlias

from typed_errs import Err, Ok, Option, Result

from pacman.analyze.events import AnalysisEvent
from pacman.analyze.runtime.operations import Operation

TaskId = NewType("TaskId", int)
AnalyzerGenerator: TypeAlias = Generator[Operation, Option[AnalysisEvent], None]


class TaskError(Enum):
    """Failures encountered while stepping an analyzer task."""

    ANALYZER_FAILED = "analyzer_failed"


@dataclass(frozen=True, slots=True)
class TaskCompleted:
    """Marker returned when a generator exits normally."""


@dataclass(slots=True)
class Task:
    """Generator plus the state required to resume it correctly."""

    id: TaskId
    generator: AnalyzerGenerator
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
                operation = next(self.generator)
                self.started = True
            else:
                operation = self.generator.send(value)
            return Ok(operation)
        except StopIteration:
            return Ok(TaskCompleted())
        except Exception:
            return Err(
                error=TaskError.ANALYZER_FAILED,
                namespace="analysis_task",
                context_msg=f"Analysis task {int(self.id)} failed",
            )
