"""High-level owner of incremental replay analysis state and tasks."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.event_extractor import (
    EventExtractorState,
    extract_batch_events,
    initial_extractor_state,
)
from pacman.analyze.events import event_tick
from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.messages import AnalysisMessage
from pacman.analyze.runtime.analyzers import (
    observe_turns,
    queue_deaths,
    schedule_turn_evaluations,
)
from pacman.analyze.runtime.context import AnalysisContext
from pacman.analyze.runtime.loop import AnalysisLoop, LoopError, RunStats
from pacman.analyze.runtime.state import RuntimeState
from pacman.analyze.simulation import SimulationRules
from pacman.replay.models import FrameBatch, Maze, ReplayId


class AnalysisRuntimeError(Enum):
    """Failures at the incremental analysis boundary."""

    INVALID_STEP_BUDGET = "invalid_step_budget"
    GRAPH_FAILED = "graph_failed"
    STATE_FAILED = "state_failed"
    WRONG_REPLAY = "wrong_replay"
    TICK_MOVED_BACKWARDS = "tick_moved_backwards"
    LOOP_FAILED = "loop_failed"
    STEP_BUDGET_EXHAUSTED = "step_budget_exhausted"


def runtime_err(error: AnalysisRuntimeError) -> Err[AnalysisRuntimeError]:
    """Create a consistently contextualized runtime error.

    Returns:
        Runtime error with stable namespace and context.
    """
    return Err(
        error=error,
        namespace="analysis_runtime",
        context_msg="Failed to process replay analysis",
    )


@dataclass(slots=True)
class AnalysisRuntime:
    """Own one replay's state, extractor cursor, and cooperative loop."""

    state: RuntimeState
    extractor: EventExtractorState
    loop: AnalysisLoop
    step_budget: int
    replay_id: Option[ReplayId]

    @classmethod
    def create(
        cls,
        maze: Maze,
        rules: SimulationRules,
        recent_capacity: int = 600,
        step_budget: int = 500,
    ) -> Result["AnalysisRuntime", AnalysisRuntimeError]:
        """Build static maze state and prime the long-lived analyzers.

        Returns:
            Initialized runtime or a typed construction error.
        """
        if step_budget <= 0:
            return runtime_err(AnalysisRuntimeError.INVALID_STEP_BUDGET)

        graph = build_maze_graph(maze)
        if isinstance(graph, Err):
            return runtime_err(AnalysisRuntimeError.GRAPH_FAILED)

        state = RuntimeState.create(maze, graph.value, rules, recent_capacity)
        if isinstance(state, Err):
            return runtime_err(AnalysisRuntimeError.STATE_FAILED)

        loop = AnalysisLoop.create()
        context = AnalysisContext()
        loop.spawn(observe_turns(context))
        loop.spawn(queue_deaths(context))
        loop.spawn(schedule_turn_evaluations(context))

        primed = loop.run_ready(step_budget)
        checked = cls._check_run(primed)
        if isinstance(checked, Err):
            return checked

        return Ok(
            cls(
                state=state.value,
                extractor=initial_extractor_state(),
                loop=loop,
                step_budget=step_budget,
                replay_id=Nothing(),
            )
        )

    def consume(
        self,
        batch: FrameBatch,
    ) -> Result[tuple[AnalysisMessage, ...], AnalysisRuntimeError]:
        """Incrementally process one immutable replay batch.

        Returns:
            Messages emitted for this batch or a typed runtime error.
        """
        if isinstance(self.replay_id, Some) and self.replay_id.value != batch.replay_id:
            return runtime_err(AnalysisRuntimeError.WRONG_REPLAY)

        next_extractor, events = extract_batch_events(
            self.extractor,
            batch,
            self.state.maze,
        )
        if events and event_tick(events[0]) < self.loop.current_tick:
            return runtime_err(AnalysisRuntimeError.TICK_MOVED_BACKWARDS)

        self.state.recent_frames.extend(batch.frames)
        self.state.collectible_changes.extend(batch.collectible_changes)

        for event in events:
            advanced = self.loop.advance_to(event_tick(event))
            if isinstance(advanced, Err):
                return runtime_err(AnalysisRuntimeError.LOOP_FAILED)
            self.loop.publish(event)
            ran = self._check_run(self.loop.run_ready(self.step_budget))
            if isinstance(ran, Err):
                return ran

        self.extractor = next_extractor
        if isinstance(self.replay_id, Nothing):
            self.replay_id = Some(batch.replay_id)
        return Ok(self.loop.drain_messages())

    @staticmethod
    def _check_run(
        result: Result[RunStats, LoopError],
    ) -> Result[None, AnalysisRuntimeError]:
        """Translate scheduler completion into the runtime error domain.

        Returns:
            Success only when every ready coroutine reached a suspension point.
        """
        if isinstance(result, Err):
            return runtime_err(AnalysisRuntimeError.LOOP_FAILED)
        if result.value.remaining_ready > 0:
            return runtime_err(AnalysisRuntimeError.STEP_BUDGET_EXHAUSTED)
        return Ok(None)
