from pacman.analyze.evaluation import EvaluationReason
from pacman.analyze.outcomes import ActionOutcome
from pacman.analyze.reasons import tactical_reasons
from pacman.replay.models import Direction
from typed_errs import Some


def outcome(
    action: Direction,
    *,
    died: bool = False,
    score: int = 0,
    power: int = 0,
    ghosts: int = 0,
    intersections: int = 1,
) -> ActionOutcome:
    return ActionOutcome(
        action,
        died,
        10,
        5,
        intersections,
        score,
        0,
        power,
        ghosts,
        0,
        Some(3),
        (),
    )


def test_safe_ghost_hunt_is_profitable() -> None:
    hunt = outcome(Direction.RIGHT, score=250, power=1, ghosts=1)

    reasons = tactical_reasons(hunt, hunt)

    assert EvaluationReason.PROFITABLE_GHOST_HUNT in reasons
    assert EvaluationReason.SAFE_SCORE_GAIN in reasons


def test_power_pellet_without_ghost_score_can_be_defensive() -> None:
    defensive = outcome(Direction.DOWN, score=50, power=1)

    assert EvaluationReason.DEFENSIVE_POWER_PELLET in tactical_reasons(defensive, defensive)


def test_losing_move_can_waste_power_pellet() -> None:
    waste = outcome(Direction.RIGHT, score=50, power=1, intersections=0)
    safe = outcome(Direction.DOWN, score=60, intersections=2)

    reasons = tactical_reasons(waste, safe)

    assert EvaluationReason.WASTED_POWER_PELLET in reasons
    assert EvaluationReason.ENTERED_TRAP in reasons


def test_dying_for_ghost_hunt_is_unsafe() -> None:
    hunt = outcome(Direction.RIGHT, died=True, score=250, power=1, ghosts=1)
    escape = outcome(Direction.DOWN, score=10)

    assert EvaluationReason.UNSAFE_GHOST_HUNT in tactical_reasons(hunt, escape)


def test_better_combo_marks_missed_ghosts() -> None:
    pellets = outcome(Direction.LEFT, score=30)
    combo = outcome(Direction.UP, score=650, power=1, ghosts=2)

    assert EvaluationReason.MISSED_GHOST_COMBO in tactical_reasons(pellets, combo)
