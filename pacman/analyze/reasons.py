"""Infer tactical explanations from compared Pac-Man action outcomes."""

from pacman.analyze.evaluation import EvaluationReason, PlayEvaluation
from pacman.analyze.outcomes import ActionOutcome, outcome_rank


def tactical_reasons(
    played: ActionOutcome,
    best: ActionOutcome,
) -> tuple[EvaluationReason, ...]:
    """Infer deterministic tactical explanations from outcome differences.

    Returns:
        Applicable reasons without duplicates.
    """
    reasons: list[EvaluationReason] = []
    played_is_best = outcome_rank(played) == outcome_rank(best)

    if played.safe_intersections == 0 and best.safe_intersections > 0:
        reasons.append(EvaluationReason.ENTERED_TRAP)
    if played.power_pellets_eaten > 0:
        if played_is_best and not played.died and played.ghosts_eaten == 0:
            reasons.append(EvaluationReason.DEFENSIVE_POWER_PELLET)
        if not played_is_best and played.ghosts_eaten == 0 and best.power_pellets_eaten == 0:
            reasons.append(EvaluationReason.WASTED_POWER_PELLET)
    if played.ghosts_eaten > 0:
        if played.died and not best.died:
            reasons.append(EvaluationReason.UNSAFE_GHOST_HUNT)
        elif played_is_best:
            reasons.append(EvaluationReason.PROFITABLE_GHOST_HUNT)
    if best.ghosts_eaten > played.ghosts_eaten:
        reasons.append(EvaluationReason.MISSED_GHOST_COMBO)
    if played_is_best and not played.died and played.score_gained > 0:
        reasons.append(EvaluationReason.SAFE_SCORE_GAIN)

    return tuple(reasons)


def explain_evaluation(evaluation: PlayEvaluation) -> PlayEvaluation:
    """Add tactical reasons to an existing feature-level evaluation.

    Returns:
        A new immutable evaluation with deduplicated reasons.
    """
    reasons = list(evaluation.reasons)
    for reason in tactical_reasons(evaluation.played, evaluation.best):
        if reason not in reasons:
            reasons.append(reason)
    return PlayEvaluation(
        evaluation.tick,
        evaluation.played,
        evaluation.best,
        evaluation.quality,
        tuple(reasons),
    )
