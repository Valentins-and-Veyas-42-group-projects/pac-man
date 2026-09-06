"""Compare a played Pac-Man action with its available alternatives."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.outcomes import ActionOutcome, best_outcome, outcome_rank
from pacman.replay.models import Direction, Tick


class PlayQuality(Enum):
    """Chess-style tactical quality assigned to one replay decision."""

    BEST = "best"
    GOOD = "good"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"
    BLUNDER = "blunder"


class EvaluationReason(Enum):
    """Structured facts explaining why a move received its quality."""

    NO_BETTER_ACTION = "no_better_action"
    FORCED_DEATH = "forced_death"
    LOST_SURVIVAL = "lost_survival"
    LOST_ESCAPE_ROUTE = "lost_escape_route"
    LOST_SAFE_TERRITORY = "lost_safe_territory"
    LOST_SCORE = "lost_score"
    SAFE_SCORE_GAIN = "safe_score_gain"
    DEFENSIVE_POWER_PELLET = "defensive_power_pellet"
    PROFITABLE_GHOST_HUNT = "profitable_ghost_hunt"
    UNSAFE_GHOST_HUNT = "unsafe_ghost_hunt"
    WASTED_POWER_PELLET = "wasted_power_pellet"
    MISSED_GHOST_COMBO = "missed_ghost_combo"
    ENTERED_TRAP = "entered_trap"


class EvaluationError(Enum):
    """Failures encountered while evaluating a played action."""

    NO_OUTCOMES = "no_outcomes"
    PLAYED_ACTION_MISSING = "played_action_missing"


@dataclass(frozen=True, slots=True)
class EvaluationPolicy:
    """Thresholds separating small losses from tactical mistakes."""

    inaccuracy_score_loss: int = 20
    inaccuracy_safe_tile_loss: int = 3
    mistake_horizon_loss: int = 3
    mistake_intersection_loss: int = 2


DEFAULT_EVALUATION_POLICY = EvaluationPolicy()


@dataclass(frozen=True, slots=True)
class PlayEvaluation:
    """Played outcome, best alternative, quality, and structured reasons."""

    tick: Tick
    played: ActionOutcome
    best: ActionOutcome
    quality: PlayQuality
    reasons: tuple[EvaluationReason, ...]


def evaluation_err(error: EvaluationError) -> Err[EvaluationError]:
    """Create an evaluation error with consistent context.

    Returns:
        A contextual evaluation error.
    """
    return Err(
        error=error,
        namespace="evaluation",
        context_msg="Failed to evaluate played action",
    )


def find_outcome(
    outcomes: tuple[ActionOutcome, ...],
    action: Direction,
) -> Option[ActionOutcome]:
    """Find the outcome belonging to one direction.

    Returns:
        The matching outcome or ``Nothing`` when it was not evaluated.
    """
    for outcome in outcomes:
        if outcome.action is action:
            return Some(outcome)
    return Nothing()


def classify_quality(
    played: ActionOutcome,
    best: ActionOutcome,
    policy: EvaluationPolicy,
) -> PlayQuality:
    """Classify tactical regret relative to the best available action.

    Returns:
        Chess-style move quality.
    """
    if outcome_rank(played) == outcome_rank(best):
        return PlayQuality.BEST
    if played.died and not best.died:
        return PlayQuality.BLUNDER
    if best.survival_horizon - played.survival_horizon >= policy.mistake_horizon_loss:
        return PlayQuality.MISTAKE
    if best.safe_intersections - played.safe_intersections >= policy.mistake_intersection_loss:
        return PlayQuality.MISTAKE
    if best.safe_tiles - played.safe_tiles >= policy.inaccuracy_safe_tile_loss:
        return PlayQuality.INACCURACY
    if best.score_gained - played.score_gained >= policy.inaccuracy_score_loss:
        return PlayQuality.INACCURACY
    return PlayQuality.GOOD


def basic_reasons(
    played: ActionOutcome,
    best: ActionOutcome,
) -> tuple[EvaluationReason, ...]:
    """Describe direct feature losses without tactical interpretation.

    Returns:
        Deterministically ordered reason values.
    """
    if outcome_rank(played) == outcome_rank(best):
        return (EvaluationReason.NO_BETTER_ACTION,)
    reasons: list[EvaluationReason] = []
    if played.died and not best.died:
        reasons.append(EvaluationReason.LOST_SURVIVAL)
    elif played.died and best.died:
        reasons.append(EvaluationReason.FORCED_DEATH)
    if played.safe_intersections < best.safe_intersections:
        reasons.append(EvaluationReason.LOST_ESCAPE_ROUTE)
    if played.safe_tiles < best.safe_tiles:
        reasons.append(EvaluationReason.LOST_SAFE_TERRITORY)
    if played.score_gained < best.score_gained:
        reasons.append(EvaluationReason.LOST_SCORE)
    return tuple(reasons)


def evaluate_play(
    tick: Tick,
    played_action: Direction,
    outcomes: tuple[ActionOutcome, ...],
    policy: EvaluationPolicy = DEFAULT_EVALUATION_POLICY,
) -> Result[PlayEvaluation, EvaluationError]:
    """Evaluate one observed action against bounded alternatives.

    Returns:
        Structured move evaluation or a typed missing-data error.
    """
    best = best_outcome(outcomes)
    if isinstance(best, Nothing):
        return evaluation_err(EvaluationError.NO_OUTCOMES)
    played = find_outcome(outcomes, played_action)
    if isinstance(played, Nothing):
        return evaluation_err(EvaluationError.PLAYED_ACTION_MISSING)
    return Ok(
        PlayEvaluation(
            tick,
            played.value,
            best.value,
            classify_quality(played.value, best.value, policy),
            basic_reasons(played.value, best.value),
        )
    )
