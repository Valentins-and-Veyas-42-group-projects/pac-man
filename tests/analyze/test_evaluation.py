from pacman.analyze.evaluation import EvaluationReason, PlayQuality, evaluate_play
from pacman.analyze.outcomes import ActionOutcome
from pacman.replay.models import Direction, Tick
from typed_errs import Some


def outcome(
    action: Direction,
    *,
    died: bool = False,
    horizon: int = 10,
    tiles: int = 5,
    intersections: int = 1,
    score: int = 0,
) -> ActionOutcome:
    return ActionOutcome(
        action,
        died,
        horizon,
        tiles,
        intersections,
        score,
        0,
        0,
        0,
        0,
        Some(2),
        (),
    )


def test_equal_play_is_best() -> None:
    played = outcome(Direction.UP)
    result = evaluate_play(Tick(4), Direction.UP, (played,)).unwrap()

    assert result.quality is PlayQuality.BEST
    assert result.reasons == (EvaluationReason.NO_BETTER_ACTION,)


def test_death_with_surviving_alternative_is_blunder() -> None:
    death = outcome(Direction.RIGHT, died=True, horizon=2, score=100)
    escape = outcome(Direction.DOWN, horizon=10)

    result = evaluate_play(Tick(8), Direction.RIGHT, (death, escape)).unwrap()

    assert result.quality is PlayQuality.BLUNDER
    assert EvaluationReason.LOST_SURVIVAL in result.reasons


def test_forced_death_is_not_blunder() -> None:
    early = outcome(Direction.RIGHT, died=True, horizon=2)
    later = outcome(Direction.DOWN, died=True, horizon=3)

    result = evaluate_play(Tick(8), Direction.RIGHT, (early, later)).unwrap()

    assert result.quality is PlayQuality.GOOD
    assert EvaluationReason.FORCED_DEATH in result.reasons


def test_missed_safe_points_is_inaccuracy() -> None:
    empty = outcome(Direction.LEFT)
    pellets = outcome(Direction.UP, score=40)

    result = evaluate_play(Tick(9), Direction.LEFT, (empty, pellets)).unwrap()

    assert result.quality is PlayQuality.INACCURACY
    assert EvaluationReason.LOST_SCORE in result.reasons


def test_large_survival_loss_is_mistake() -> None:
    short = outcome(Direction.LEFT, horizon=5)
    long = outcome(Direction.UP, horizon=10)

    assert (
        evaluate_play(Tick(9), Direction.LEFT, (short, long)).unwrap().quality
        is PlayQuality.MISTAKE
    )
