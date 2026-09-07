"""Mutable replay state owned exclusively by one analysis runtime."""

from collections import deque
from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Ok, Result

from pacman.analyze.evaluation import PlayEvaluation
from pacman.analyze.models import MazeGraph
from pacman.analyze.simulation import SimulationRules
from pacman.replay.models import CollectibleChange, Frame, Maze


class RuntimeStateError(Enum):
    """Failures encountered while constructing analysis runtime state."""

    INVALID_RECENT_CAPACITY = "invalid_recent_capacity"
    DIMENSION_MISMATCH = "dimension_mismatch"
    NODE_COUNT_MISMATCH = "node_count_mismatch"


def runtime_state_err(error: RuntimeStateError) -> Err[RuntimeStateError]:
    """Create a runtime-state error with consistent context.

    Returns:
        A contextual runtime-state error.
    """
    return Err(
        error=error,
        namespace="analysis_runtime_state",
        context_msg="Failed to construct analysis runtime state",
    )


@dataclass(slots=True)
class RuntimeState:
    """Maze context and incremental replay data owned by the worker."""

    maze: Maze
    graph: MazeGraph
    rules: SimulationRules

    recent_frames: deque[Frame]
    collectible_changes: list[CollectibleChange]
    evaluations: list[PlayEvaluation]

    @classmethod
    def create(
        cls,
        maze: Maze,
        graph: MazeGraph,
        rules: SimulationRules,
        recent_capacity: int,
    ) -> Result["RuntimeState", RuntimeStateError]:
        """Validate static context and allocate empty incremental storage.

        Returns:
            Initialized runtime state or a typed validation error.
        """
        if recent_capacity <= 0:
            return runtime_state_err(RuntimeStateError.INVALID_RECENT_CAPACITY)
        if graph.width != maze.width or graph.height != maze.height:
            return runtime_state_err(RuntimeStateError.DIMENSION_MISMATCH)
        if len(graph.moves) != maze.width * maze.height:
            return runtime_state_err(RuntimeStateError.NODE_COUNT_MISMATCH)
        return Ok(
            cls(
                maze=maze,
                graph=graph,
                rules=rules,
                recent_frames=deque(maxlen=recent_capacity),
                collectible_changes=[],
                evaluations=[],
            )
        )
