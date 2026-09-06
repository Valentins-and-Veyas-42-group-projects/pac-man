"""Explore bounded Pac-Man counterfactuals over predicted ghost movement."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.collectibles import CollectibleField
from pacman.analyze.models import MazeGraph, Move
from pacman.analyze.prediction import GhostPrediction, PredictedGhostState
from pacman.replay.models import Collectible, Direction, Ghost, GhostState, TileIndex


class SimulationError(Enum):
    """Failures encountered while simulating a player action."""

    INVALID_ORIGIN = "invalid_origin"
    ILLEGAL_ACTION = "illegal_action"
    INVALID_HORIZON = "invalid_horizon"
    FIELD_SIZE_MISMATCH = "field_size_mismatch"


@dataclass(frozen=True, slots=True)
class SimulationRules:
    """Explicit scoring and duration rules used by bounded simulation."""

    horizon_ticks: int = 12
    pacgum_score: int = 10
    power_pellet_score: int = 50
    frightened_ticks: int = 8
    ghost_combo_scores: tuple[int, ...] = (200, 400, 800, 1600)


@dataclass(frozen=True, slots=True)
class SimulationState:
    """One immutable player branch at a relative simulation tick."""

    tile: TileIndex
    direction: Direction
    tick: int
    collectibles: tuple[Collectible, ...]
    frightened_remaining: int
    ghost_combo: int
    score_gained: int
    pacgums_eaten: int
    power_pellets_eaten: int
    eaten_ghosts: frozenset[Ghost]
    died: bool
    path: tuple[TileIndex, ...]


@dataclass(frozen=True, slots=True)
class ActionSimulation:
    """Terminal branches produced for one required first action."""

    action: Direction
    terminals: tuple[SimulationState, ...]


def simulation_err(error: SimulationError) -> Err[SimulationError]:
    """Create a simulation error with consistent context.

    Returns:
        A contextual simulation error.
    """
    return Err(
        error=error,
        namespace="simulation",
        context_msg="Failed to simulate player action",
    )


def first_move(graph: MazeGraph, origin: TileIndex, action: Direction) -> Option[Move]:
    """Find the graph move representing one action.

    Returns:
        The matching move or ``Nothing`` when the action is illegal.
    """
    for move in graph.neighbors(origin):
        if move.direction is action:
            return Some(move)
    return Nothing()


def ghosts_at(
    predictions: tuple[GhostPrediction, ...],
    tile: TileIndex,
    tick: int,
) -> tuple[PredictedGhostState, ...]:
    """Return predicted ghosts occupying one tile at one relative tick."""
    states: list[PredictedGhostState] = []
    for prediction in predictions:
        if tick < len(prediction.ticks):
            states.extend(state for state in prediction.ticks[tick] if state.tile == tile)
    return tuple(states)


def advance_state(
    state: SimulationState,
    move: Move,
    predictions: tuple[GhostPrediction, ...],
    rules: SimulationRules,
) -> SimulationState:
    """Advance one immutable branch by one graph move.

    Returns:
        The advanced immutable simulation state.
    """
    tick = state.tick + 1
    tile = move.destination
    collectibles = list(state.collectibles)
    collectible = collectibles[int(tile)]
    frightened = max(0, state.frightened_remaining - 1)
    combo = state.ghost_combo if frightened > 0 else 0
    score = state.score_gained
    pacgums = state.pacgums_eaten
    power_pellets = state.power_pellets_eaten

    if collectible is Collectible.PACGUM:
        collectibles[int(tile)] = Collectible.NONE
        score += rules.pacgum_score
        pacgums += 1
    elif collectible is Collectible.POWER_PELLET:
        collectibles[int(tile)] = Collectible.NONE
        score += rules.power_pellet_score
        power_pellets += 1
        frightened = rules.frightened_ticks
        combo = 0

    eaten = set(state.eaten_ghosts)
    died = False
    for ghost in ghosts_at(predictions, tile, tick):
        if ghost.ghost in eaten or ghost.state is GhostState.EATEN:
            continue
        if frightened > 0 or ghost.state is GhostState.FRIGHTENED:
            if rules.ghost_combo_scores:
                reward_index = min(combo, len(rules.ghost_combo_scores) - 1)
                score += rules.ghost_combo_scores[reward_index]
            combo += 1
            eaten.add(ghost.ghost)
        elif ghost.dangerous:
            died = True

    return SimulationState(
        tile,
        move.direction,
        tick,
        tuple(collectibles),
        frightened,
        combo,
        score,
        pacgums,
        power_pellets,
        frozenset(eaten),
        died,
        (*state.path, tile),
    )


def state_key(state: SimulationState) -> tuple[object, ...]:
    """Return the tactical identity used to deduplicate search branches."""
    return (
        state.tile,
        state.direction,
        state.tick,
        state.collectibles,
        state.frightened_remaining,
        state.ghost_combo,
        state.eaten_ghosts,
        state.died,
    )


def simulate_action(
    graph: MazeGraph,
    collectibles: CollectibleField,
    predictions: tuple[GhostPrediction, ...],
    origin: TileIndex,
    direction: Direction,
    rules: SimulationRules,
) -> Result[ActionSimulation, SimulationError]:
    """Explore continuations after requiring one initial player action.

    Returns:
        Terminal branches or a typed validation error.
    """
    if not graph.contains(origin):
        return simulation_err(SimulationError.INVALID_ORIGIN)
    if len(collectibles.tiles) != len(graph.moves):
        return simulation_err(SimulationError.FIELD_SIZE_MISMATCH)
    if rules.horizon_ticks < 1 or rules.frightened_ticks < 0:
        return simulation_err(SimulationError.INVALID_HORIZON)
    first = first_move(graph, origin, direction)
    if isinstance(first, Nothing):
        return simulation_err(SimulationError.ILLEGAL_ACTION)

    initial = SimulationState(
        origin,
        direction,
        0,
        collectibles.tiles,
        0,
        0,
        0,
        0,
        0,
        frozenset(),
        False,
        (origin,),
    )
    frontier = [advance_state(initial, first.value, predictions, rules)]
    terminals: list[SimulationState] = []

    while frontier:
        next_frontier: dict[tuple[object, ...], SimulationState] = {}
        for state in frontier:
            if state.died or state.tick >= rules.horizon_ticks:
                terminals.append(state)
                continue
            moves = graph.neighbors(state.tile)
            if not moves:
                terminals.append(state)
                continue
            for move in moves:
                advanced = advance_state(state, move, predictions, rules)
                key = state_key(advanced)
                if key not in next_frontier:
                    next_frontier[key] = advanced
                    continue
                if advanced.score_gained > next_frontier[key].score_gained:
                    next_frontier[key] = advanced
        frontier = list(next_frontier.values())

    return Ok(ActionSimulation(direction, tuple(terminals)))
