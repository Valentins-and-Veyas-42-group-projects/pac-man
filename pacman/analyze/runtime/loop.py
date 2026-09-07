"""Fair cooperative scheduler for generator-based analysis tasks."""

from collections import deque
from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.events import AnalysisEvent
from pacman.analyze.messages import AnalysisMessage
from pacman.analyze.runtime.operations import Emit, WaitForEvent
from pacman.analyze.runtime.task import AnalyzerGenerator, Task, TaskCompleted, TaskId


class LoopError(Enum):
    """Failures encountered while running cooperative tasks."""

    INVALID_STEP_BUDGET = "invalid_step_budget"
    TASK_FAILED = "task_failed"


@dataclass(frozen=True, slots=True)
class ResumeTask:
    """One task and the optional event used for its next step."""

    task_id: TaskId
    event: Option[AnalysisEvent]


@dataclass(frozen=True, slots=True)
class RunStats:
    """Work performed during one bounded scheduler run."""

    steps: int
    remaining_ready: int


@dataclass(slots=True)
class AnalysisLoop:
    """Own ready tasks, event waiters, and emitted messages."""

    _tasks: dict[TaskId, Task]
    _ready: deque[ResumeTask]
    _waiters: dict[type[object], list[TaskId]]
    _messages: list[AnalysisMessage]
    _next_task_id: int

    @classmethod
    def create(cls) -> "AnalysisLoop":
        """Create an empty scheduler.

        Returns:
            A scheduler with no tasks or messages.
        """
        return cls({}, deque(), {}, [], 0)

    def spawn(self, generator: AnalyzerGenerator) -> TaskId:
        """Register a generator and queue its initial step.

        Returns:
            Stable identifier assigned to the new task.
        """
        task_id = TaskId(self._next_task_id)
        self._next_task_id += 1
        self._tasks[task_id] = Task(task_id, generator)
        self._ready.append(ResumeTask(task_id, Nothing()))
        return task_id

    def publish(self, event: AnalysisEvent) -> int:
        """Wake every task waiting for the concrete event type.

        Returns:
            Number of tasks made ready.
        """
        waiting = self._waiters.pop(type(event), [])
        for task_id in waiting:
            self._ready.append(ResumeTask(task_id, Some(event)))
        return len(waiting)

    def run_ready(self, step_budget: int) -> Result[RunStats, LoopError]:
        """Run ready tasks fairly until idle or the budget is exhausted.

        Returns:
            Work statistics or a typed scheduler error.
        """
        if step_budget < 0:
            return Err(
                error=LoopError.INVALID_STEP_BUDGET,
                namespace="analysis_loop",
                context_msg="Step budget must not be negative",
            )

        steps = 0
        while self._ready and steps < step_budget:
            resume = self._ready.popleft()
            task = self._tasks[resume.task_id]
            result = task.step(resume.event)
            steps += 1
            if isinstance(result, Err):
                return Err(
                    error=LoopError.TASK_FAILED,
                    namespace="analysis_loop",
                    context_msg=f"Analysis task {int(task.id)} failed",
                )
            operation = result.value
            if isinstance(operation, TaskCompleted):
                del self._tasks[task.id]
            elif isinstance(operation, WaitForEvent):
                self._waiters.setdefault(operation.event_type, []).append(task.id)
            elif isinstance(operation, Emit):
                self._messages.append(operation.message)
                self._ready.append(ResumeTask(task.id, Nothing()))

        return Ok(RunStats(steps, len(self._ready)))

    def drain_messages(self) -> tuple[AnalysisMessage, ...]:
        """Remove and return every emitted analysis message.

        Returns:
            Messages in emission order.
        """
        messages = tuple(self._messages)
        self._messages.clear()
        return messages
