from pacman.analyze.outcomes import ActionOutcome, best_outcome, rank_outcomes
from pacman.replay.models import Direction
from typed_errs import Nothing, Some


def outcome(
    action: Direction,
    *,
    died: bool = False,
    horizon: int = 10,
    safe_tiles: int = 4,
    intersections: int = 1,
    score: int = 0,
    ghosts: int = 0,
) -> ActionOutcome:
    return ActionOutcome(
        action,
        died,
        horizon,
        safe_tiles,
        intersections,
        score,
        score // 10,
        0,
        ghosts,
        0,
        Some(2),
        (),
    )


def test_survival_beats_a_higher_scoring_death() -> None:
    safe = outcome(Direction.UP, score=10)
    death = outcome(Direction.RIGHT, died=True, horizon=2, score=1000, ghosts=2)

    assert rank_outcomes((death, safe)) == (safe, death)


def test_escape_options_beat_points_when_survival_is_equal() -> None:
    open_route = outcome(Direction.DOWN, intersections=2, score=10)
    narrow_route = outcome(Direction.RIGHT, intersections=0, score=100)

    assert best_outcome((narrow_route, open_route)) == Some(open_route)


def test_score_breaks_ties_after_tactical_features() -> None:
    pellets = outcome(Direction.LEFT, score=30)
    empty = outcome(Direction.UP, score=0)

    assert rank_outcomes((empty, pellets)) == (pellets, empty)


def test_safe_ghost_combo_can_trade_a_small_amount_of_territory() -> None:
    combo = outcome(Direction.RIGHT, intersections=0, score=250, ghosts=1)
    pellets = outcome(Direction.DOWN, intersections=1, score=20)

    assert rank_outcomes((pellets, combo)) == (combo, pellets)


def test_empty_outcomes_have_no_best_action() -> None:
    assert isinstance(best_outcome(()), Nothing)
