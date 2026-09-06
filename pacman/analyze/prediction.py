"""Predict bounded ghost movement while respecting current direction."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Ok, Result

from pacman.analyze.models import MazeGraph, Move
from pacman.analyze.threat import NO_THREAT, ThreatField
from pacman.replay.models import Direction, Ghost, GhostFrame, GhostState, Maze, TileIndex

OPPOSITE: dict[Direction, Direction] = {
    Direction.UP: Direction.DOWN,
    Direction.RIGHT: Direction.LEFT,
    Direction.DOWN: Direction.UP,
    Direction.LEFT: Direction.RIGHT,
}


class PredictionError(Enum):
    """Failures encountered while predicting ghost movement."""

    INVALID_GHOST_TILE = "invalid_ghost_tile"
    INVALID_HORIZON = "invalid_horizon"


@dataclass(frozen=True, slots=True)
class PredictedGhostState:
    """One possible ghost state at a future relative tick."""

    ghost: Ghost
    tile: TileIndex
    direction: Direction
    tick: int
    dangerous: bool


@dataclass(frozen=True, slots=True)
class GhostPrediction:
    """Possible states grouped by relative prediction tick."""

    ghost: Ghost
    ticks: tuple[tuple[PredictedGhostState, ...], ...]


def prediction_err(error: PredictionError) -> Err[PredictionError]:
    """Create a prediction error with consistent context.

    Returns:
        A contextual prediction error.
    """
    return Err(
        error=error,
        namespace="prediction",
        context_msg="Failed to predict ghost movement",
    )


def legal_ghost_moves(
    graph: MazeGraph,
    tile: TileIndex,
    direction: Direction,
) -> tuple[Move, ...]:
    """Return moves excluding reversal unless reversal is the only choice."""
    moves = graph.neighbors(tile)
    forward = tuple(move for move in moves if move.direction is not OPPOSITE[direction])
    return forward if forward else moves


def predict_ghost(
    graph: MazeGraph,
    maze: Maze,
    ghost: GhostFrame,
    horizon: int,
) -> Result[GhostPrediction, PredictionError]:
    """Enumerate possible direction-constrained ghost states through a horizon.

    Returns:
        A bounded immutable prediction or a typed validation error.
    """
    if horizon < 0:
        return prediction_err(PredictionError.INVALID_HORIZON)
    origin = maze.tile_index(ghost.position)
    if not graph.contains(origin):
        return prediction_err(PredictionError.INVALID_GHOST_TILE)

    dangerous = ghost.state not in (GhostState.FRIGHTENED, GhostState.EATEN)
    current = (PredictedGhostState(ghost.ghost, origin, ghost.direction, 0, dangerous),)
    ticks: list[tuple[PredictedGhostState, ...]] = [current]

    for tick in range(1, horizon + 1):
        next_states: dict[tuple[TileIndex, Direction], PredictedGhostState] = {}
        for state in current:
            for move in legal_ghost_moves(graph, state.tile, state.direction):
                predicted = PredictedGhostState(
                    ghost=state.ghost,
                    tile=move.destination,
                    direction=move.direction,
                    tick=tick,
                    dangerous=state.dangerous,
                )
                next_states[(predicted.tile, predicted.direction)] = predicted
        current = tuple(next_states.values())
        ticks.append(current)

    return Ok(GhostPrediction(ghost.ghost, tuple(ticks)))


def build_predicted_threat_field(
    graph: MazeGraph,
    maze: Maze,
    ghosts: tuple[GhostFrame, ...],
    horizon: int,
) -> Result[ThreatField, PredictionError]:
    """Combine earliest dangerous arrivals from bounded ghost predictions.

    Returns:
        A threat field or a typed prediction error.
    """
    if horizon < 0:
        return prediction_err(PredictionError.INVALID_HORIZON)

    etas = [NO_THREAT] * len(graph.moves)
    owners: list[list[Ghost]] = [[] for _ in graph.moves]
    for ghost in ghosts:
        prediction = predict_ghost(graph, maze, ghost, horizon)
        if isinstance(prediction, Err):
            return prediction
        for states in prediction.value.ticks:
            for state in states:
                if not state.dangerous:
                    continue
                index = int(state.tile)
                if etas[index] == NO_THREAT or state.tick < etas[index]:
                    etas[index] = state.tick
                    owners[index] = [state.ghost]
                elif state.tick == etas[index] and state.ghost not in owners[index]:
                    owners[index].append(state.ghost)

    return Ok(ThreatField(tuple(etas), tuple(tuple(value) for value in owners)))
