from pacman.analyze.evaluation import PlayEvaluation, PlayQuality
from pacman.analyze.outcomes import ActionOutcome
from pacman.analyze.timeline import summarize_replay
from pacman.replay.models import Direction, Tick
from typed_errs import Some


def outcome(action: Direction, *, died: bool = False, horizon: int = 10) -> ActionOutcome:
    return ActionOutcome(
        action,
        died,
        horizon,
        5,
        1,
        0,
        0,
        0,
        0,
        0,
        Some(2),
        (),
    )


def evaluation(tick: int, quality: PlayQuality) -> PlayEvaluation:
    played = outcome(Direction.RIGHT, died=quality is PlayQuality.BLUNDER, horizon=3)
    best = outcome(Direction.DOWN, horizon=10)
    return PlayEvaluation(Tick(tick), played, best, quality, ())


def test_summary_counts_quality_and_ranks_critical_moments() -> None:
    summary = summarize_replay(
        (
            evaluation(10, PlayQuality.BEST),
            evaluation(20, PlayQuality.INACCURACY),
            evaluation(30, PlayQuality.MISTAKE),
            evaluation(40, PlayQuality.BLUNDER),
        ),
        critical_limit=2,
    )

    assert summary.best_moves == 1
    assert summary.inaccuracies == 1
    assert summary.mistakes == 1
    assert summary.blunders == 1
    assert summary.critical_moments == (Tick(40), Tick(30))


def test_repeated_tick_keeps_worse_evaluation() -> None:
    summary = summarize_replay((
        evaluation(10, PlayQuality.INACCURACY),
        evaluation(10, PlayQuality.BLUNDER),
    ))

    assert len(summary.decisions) == 1
    assert summary.decisions[0].quality is PlayQuality.BLUNDER


def test_negative_critical_limit_returns_no_moments() -> None:
    summary = summarize_replay((evaluation(10, PlayQuality.BLUNDER),), -1)

    assert summary.critical_moments == ()
