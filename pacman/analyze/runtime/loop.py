"""Fair cooperative scheduler for generator-based analysis tasks."""

import heapq
from collections import deque
from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.events import AnalysisEvent
from pacman.analyze.messages import AnalysisMessage
from pacman.analyze.runtime.operations import (
    AnalyzerCoroutine,
    Emit,
    SleepUntil,
    Spawn,
    WaitForEvent,
    YieldNow,
)
from pacman.analyze.runtime.task import (
    Task,
    TaskCompleted,
    TaskId,
)
from pacman.replay.models import Tick


class LoopError(Enum):
    """Failures encountered while running cooperative tasks."""

    INVALID_STEP_BUDGET = "invalid_step_budget"
    TASK_FAILED = "task_failed"
    TICK_MOVED_BACKWARDS = "tick_moved_backwards"


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


@dataclass(frozen=True, slots=True, order=True)
class ScheduledTask:
    """Task sleeping until a deterministic replay tick."""

    tick: Tick
    order: int
    task_id: TaskId


@dataclass(slots=True)
class AnalysisLoop:
    """Own ready tasks, event waiters, and emitted messages."""

    _tasks: dict[TaskId, Task]
    _ready: deque[ResumeTask]
    _waiters: dict[type[object], list[TaskId]]
    _scheduled: list[ScheduledTask]
    _messages: list[AnalysisMessage]

    _current_tick: Tick
    _next_task_id: int
    _next_schedule_order: int

    @classmethod
    def create(cls) -> "AnalysisLoop":
        """Create an empty scheduler.

        Returns:
            A scheduler with no tasks or messages.
        """
        return cls(
            _tasks={},
            _ready=deque(),
            _waiters={},
            _scheduled=[],
            _messages=[],
            _current_tick=Tick(0),
            _next_task_id=0,
            _next_schedule_order=0,
        )

    def spawn(self, coroutine: AnalyzerCoroutine) -> TaskId:
        """Register a native coroutine and queue its initial step.

        Returns:
            Stable identifier assigned to the new task.
        """
        task_id = TaskId(self._next_task_id)
        self._next_task_id += 1
        self._tasks[task_id] = Task(task_id, coroutine)
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
            elif isinstance(operation, SleepUntil):
                if operation.tick <= self._current_tick:
                    self._ready.append(
                        ResumeTask(
                            task_id=task.id,
                            event=Nothing(),
                        )
                    )
                else:
                    heapq.heappush(
                        self._scheduled,
                        ScheduledTask(
                            tick=operation.tick,
                            order=self._next_schedule_order,
                            task_id=task.id,
                        ),
                    )
                    self._next_schedule_order += 1

            elif isinstance(operation, Emit):
                self._messages.append(operation.message)
                self._ready.append(ResumeTask(task.id, Nothing()))
            elif isinstance(operation, Spawn):
                self.spawn(operation.coroutine)
                self._ready.append(ResumeTask(task.id, Nothing()))
            elif isinstance(operation, YieldNow):
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

    def advance_to(self, tick: Tick) -> Result[int, LoopError]:
        """Advance replay time and wake every due task.

        Returns:
            Number of tasks moved into the ready queue.
        """
        if tick < self._current_tick:
            return Err(
                error=LoopError.TICK_MOVED_BACKWARDS,
                namespace="analysis_loop",
                context_msg=(
                    f"Cannot move analysis clock from {int(self._current_tick)} to {int(tick)}"
                ),
            )

        self._current_tick = tick
        awakened = 0
        while self._scheduled:
            scheduled = self._scheduled[0]

            if scheduled.tick > tick:
                break

            heapq.heappop(self._scheduled)

            if scheduled.task_id not in self._tasks:
                continue

            self._ready.append(ResumeTask(scheduled.task_id, Nothing()))
            awakened += 1

        return Ok(awakened)

    @property
    def current_tick(self) -> Tick:
        """Current deterministic replay tick."""
        return self._current_tick

    @property
    def sleeping_count(self) -> int:
        """Number of tasks sleeping until future replay ticks."""
        return len(self._scheduled)
