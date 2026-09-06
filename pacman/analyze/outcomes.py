"""Summarize and rank bounded action simulations."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.options import ActionEvaluation
from pacman.analyze.simulation import ActionSimulation, SimulationState
from pacman.replay.models import Direction, TileIndex


class OutcomeError(Enum):
    """Failures encountered while producing tactical outcomes."""

    NO_TERMINAL_STATES = "no_terminal_states"


@dataclass(frozen=True, slots=True)
class OutcomePolicy:
    """Weights for tactical tradeoffs after survival has been secured."""

    safe_tile_value: int = 5
    safe_intersection_value: int = 50
    threat_margin_value: int = 10
    unthreatened_bonus: int = 20


DEFAULT_OUTCOME_POLICY = OutcomePolicy()


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    """Comparable tactical result for one legal first action."""

    action: Direction
    died: bool
    survival_horizon: int
    safe_tiles: int
    safe_intersections: int
    score_gained: int
    pacgums_eaten: int
    power_pellets_eaten: int
    ghosts_eaten: int
    remaining_power_ticks: int
    threat_margin: Option[int]
    path: tuple[TileIndex, ...]


def outcome_err(error: OutcomeError) -> Err[OutcomeError]:
    """Create an outcome error with consistent context.

    Returns:
        A contextual outcome error.
    """
    return Err(
        error=error,
        namespace="outcomes",
        context_msg="Failed to summarize action outcome",
    )


def terminal_rank(state: SimulationState) -> tuple[int, ...]:
    """Return the survival-first ordering key for a terminal branch.

    Returns:
        A key whose larger values represent better branches.
    """
    return (
        int(not state.died),
        state.tick,
        state.score_gained,
        len(state.eaten_ghosts),
        state.frightened_remaining,
        state.pacgums_eaten,
    )


def summarize_simulation(
    simulation: ActionSimulation,
    safety: Option[ActionEvaluation],
) -> Result[ActionOutcome, OutcomeError]:
    """Summarize the best available continuation of one first action.

    Returns:
        A comparable action outcome or a missing-terminal error.
    """
    if not simulation.terminals:
        return outcome_err(OutcomeError.NO_TERMINAL_STATES)
    terminal = max(simulation.terminals, key=terminal_rank)
    safe_tiles = 0
    safe_intersections = 0
    margin: Option[int] = Nothing()
    if isinstance(safety, Some):
        safe_tiles = safety.value.safe_tiles
        safe_intersections = safety.value.safe_intersections
        margin = safety.value.minimum_margin

    return Ok(
        ActionOutcome(
            action=simulation.action,
            died=terminal.died,
            survival_horizon=terminal.tick,
            safe_tiles=safe_tiles,
            safe_intersections=safe_intersections,
            score_gained=terminal.score_gained,
            pacgums_eaten=terminal.pacgums_eaten,
            power_pellets_eaten=terminal.power_pellets_eaten,
            ghosts_eaten=len(terminal.eaten_ghosts),
            remaining_power_ticks=terminal.frightened_remaining,
            threat_margin=margin,
            path=terminal.path,
        )
    )


def outcome_rank(
    outcome: ActionOutcome,
    policy: OutcomePolicy = DEFAULT_OUTCOME_POLICY,
) -> tuple[int, ...]:
    """Return the tactical ordering key for an action outcome.

    Returns:
        A key whose larger values represent better actions.
    """
    margin_value = 0
    if isinstance(outcome.threat_margin, Some):
        margin_value = outcome.threat_margin.value * policy.threat_margin_value
    elif outcome.safe_tiles > 0:
        margin_value = policy.unthreatened_bonus
    tactical_value = (
        outcome.safe_intersections * policy.safe_intersection_value
        + outcome.safe_tiles * policy.safe_tile_value
        + margin_value
        + outcome.score_gained
    )
    return (
        int(not outcome.died),
        outcome.survival_horizon,
        tactical_value,
        outcome.score_gained,
        outcome.ghosts_eaten,
        outcome.safe_intersections,
        outcome.safe_tiles,
        outcome.remaining_power_ticks,
    )


def rank_outcomes(outcomes: tuple[ActionOutcome, ...]) -> tuple[ActionOutcome, ...]:
    """Order outcomes from tactically strongest to weakest.

    Returns:
        Stable survival-first ordering of the supplied outcomes.
    """
    return tuple(sorted(outcomes, key=outcome_rank, reverse=True))


def best_outcome(outcomes: tuple[ActionOutcome, ...]) -> Option[ActionOutcome]:
    """Select the strongest available outcome.

    Returns:
        The best outcome or ``Nothing`` for an empty collection.
    """
    ranked = rank_outcomes(outcomes)
    if not ranked:
        return Nothing()
    return Some(ranked[0])
