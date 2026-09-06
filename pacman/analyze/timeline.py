"""Reduce evaluated Pac-Man decisions into a replay-level summary."""

from dataclasses import dataclass

from pacman.analyze.evaluation import PlayEvaluation, PlayQuality
from pacman.replay.models import Tick

QUALITY_SEVERITY: dict[PlayQuality, int] = {
    PlayQuality.BEST: 0,
    PlayQuality.GOOD: 1,
    PlayQuality.INACCURACY: 2,
    PlayQuality.MISTAKE: 3,
    PlayQuality.BLUNDER: 4,
}


@dataclass(frozen=True, slots=True)
class ReplayEvaluation:
    """Immutable decision summary and ranked critical replay ticks."""

    decisions: tuple[PlayEvaluation, ...]
    best_moves: int
    good_moves: int
    inaccuracies: int
    mistakes: int
    blunders: int
    critical_moments: tuple[Tick, ...]


def evaluation_loss(evaluation: PlayEvaluation) -> tuple[int, ...]:
    """Return a key measuring tactical loss for critical-moment ranking.

    Returns:
        A larger-is-worse deterministic loss key.
    """
    return (
        QUALITY_SEVERITY[evaluation.quality],
        int(evaluation.played.died and not evaluation.best.died),
        evaluation.best.survival_horizon - evaluation.played.survival_horizon,
        evaluation.best.safe_intersections - evaluation.played.safe_intersections,
        evaluation.best.safe_tiles - evaluation.played.safe_tiles,
        evaluation.best.score_gained - evaluation.played.score_gained,
    )


def deduplicate_decisions(
    evaluations: tuple[PlayEvaluation, ...],
) -> tuple[PlayEvaluation, ...]:
    """Keep the largest tactical loss when a tick was evaluated repeatedly.

    Returns:
        Tick-ordered unique decisions.
    """
    by_tick: dict[Tick, PlayEvaluation] = {}
    for evaluation in evaluations:
        if evaluation.tick not in by_tick:
            by_tick[evaluation.tick] = evaluation
            continue
        if evaluation_loss(evaluation) > evaluation_loss(by_tick[evaluation.tick]):
            by_tick[evaluation.tick] = evaluation
    return tuple(by_tick[tick] for tick in sorted(by_tick, key=int))


def summarize_replay(
    evaluations: tuple[PlayEvaluation, ...],
    critical_limit: int = 5,
) -> ReplayEvaluation:
    """Count move quality and retain the replay's largest tactical losses.

    Returns:
        Immutable replay summary.
    """
    decisions = deduplicate_decisions(evaluations)
    candidates = tuple(
        evaluation
        for evaluation in decisions
        if evaluation.quality not in (PlayQuality.BEST, PlayQuality.GOOD)
    )
    critical = tuple(
        evaluation.tick
        for evaluation in sorted(candidates, key=evaluation_loss, reverse=True)[
            : max(0, critical_limit)
        ]
    )
    return ReplayEvaluation(
        decisions=decisions,
        best_moves=sum(value.quality is PlayQuality.BEST for value in decisions),
        good_moves=sum(value.quality is PlayQuality.GOOD for value in decisions),
        inaccuracies=sum(value.quality is PlayQuality.INACCURACY for value in decisions),
        mistakes=sum(value.quality is PlayQuality.MISTAKE for value in decisions),
        blunders=sum(value.quality is PlayQuality.BLUNDER for value in decisions),
        critical_moments=critical,
    )
