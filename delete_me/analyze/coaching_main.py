"""Run one disposable end-to-end tactical coaching scenario."""

from pacman.analyze.collectibles import CollectibleField
from pacman.analyze.evaluation import PlayEvaluation, evaluate_play
from pacman.analyze.models import MazeGraph, Move
from pacman.analyze.options import ActionEvaluation, evaluate_actions
from pacman.analyze.outcomes import ActionOutcome, summarize_simulation
from pacman.analyze.prediction import GhostPrediction, PredictedGhostState
from pacman.analyze.reasons import explain_evaluation
from pacman.analyze.simulation import SimulationRules, simulate_action
from pacman.analyze.threat import NO_THREAT, ThreatField
from pacman.analyze.timeline import summarize_replay
from pacman.replay.models import Collectible, Direction, Ghost, GhostState, Tick, TileIndex
from typed_errs import Err, Nothing, Option, Some


def demo_graph() -> MazeGraph:
    """Build the small branching graph used by the coaching demo.

    Returns:
        A six-tile graph with two initial player choices.
    """
    return MazeGraph(
        3,
        2,
        (
            (Move(TileIndex(1), Direction.RIGHT), Move(TileIndex(3), Direction.DOWN)),
            (Move(TileIndex(0), Direction.LEFT), Move(TileIndex(2), Direction.RIGHT)),
            (Move(TileIndex(1), Direction.LEFT),),
            (Move(TileIndex(0), Direction.UP), Move(TileIndex(4), Direction.RIGHT)),
            (Move(TileIndex(3), Direction.LEFT), Move(TileIndex(5), Direction.RIGHT)),
            (Move(TileIndex(4), Direction.LEFT),),
        ),
    )


def predicted_contact(
    ghost: Ghost,
    tile: TileIndex,
    tick: int,
    state: GhostState,
) -> GhostPrediction:
    """Build one sparse predicted contact for the coaching demo.

    Returns:
        A prediction containing the requested ghost state.
    """
    ticks: list[tuple[PredictedGhostState, ...]] = [() for _ in range(tick + 1)]
    ticks[tick] = (PredictedGhostState(ghost, tile, Direction.LEFT, tick, state),)
    return GhostPrediction(ghost, tuple(ticks))


def option_for(
    options: tuple[ActionEvaluation, ...],
    direction: Direction,
) -> Option[ActionEvaluation]:
    """Find safety facts for one action.

    Returns:
        Matching safety facts or ``Nothing``.
    """
    for option in options:
        if option.action is direction:
            return Some(option)
    return Nothing()


def render_evaluation(evaluation: PlayEvaluation) -> None:
    """Print one compact chess-style move evaluation."""
    print(f"played:  {evaluation.played.action.name}")
    print(f"best:    {evaluation.best.action.name}")
    print(f"quality: {evaluation.quality.value}")
    print("reasons: " + ", ".join(reason.value for reason in evaluation.reasons))


def run() -> int:
    """Compose analysis primitives for one synthetic tactical position.

    Returns:
        Zero on success or one when an algorithm rejects the scenario.
    """
    graph = demo_graph()
    collectibles = CollectibleField((
        Collectible.NONE,
        Collectible.PACGUM,
        Collectible.NONE,
        Collectible.PACGUM,
        Collectible.PACGUM,
        Collectible.NONE,
    ))
    predictions = (
        predicted_contact(Ghost.BLINKY, TileIndex(1), 1, GhostState.CHASE),
        predicted_contact(Ghost.PINKY, TileIndex(4), 2, GhostState.FRIGHTENED),
    )
    threats = ThreatField(
        (NO_THREAT, 1, NO_THREAT, NO_THREAT, NO_THREAT, NO_THREAT),
        ((), (Ghost.BLINKY,), (), (), (), ()),
    )
    options = evaluate_actions(graph, threats, TileIndex(0))
    if isinstance(options, Err):
        options.print_diagnostic()
        return 1

    outcomes: list[ActionOutcome] = []
    for move in graph.neighbors(TileIndex(0)):
        simulation = simulate_action(
            graph,
            collectibles,
            predictions,
            TileIndex(0),
            move.direction,
            SimulationRules(horizon_ticks=3),
        )
        if isinstance(simulation, Err):
            simulation.print_diagnostic()
            return 1
        outcome = summarize_simulation(
            simulation.value,
            option_for(options.value, move.direction),
        )
        if isinstance(outcome, Err):
            outcome.print_diagnostic()
            return 1
        outcomes.append(outcome.value)

    evaluation = evaluate_play(Tick(100), Direction.RIGHT, tuple(outcomes))
    if isinstance(evaluation, Err):
        evaluation.print_diagnostic()
        return 1
    explained = explain_evaluation(evaluation.value)
    replay = summarize_replay((explained,))

    print("scenario: RIGHT meets Blinky; DOWN reaches frightened Pinky")
    for outcome in outcomes:
        print(
            f"{outcome.action.name:<5} died={str(outcome.died):<5} "
            f"horizon={outcome.survival_horizon} score={outcome.score_gained} "
            f"safe_tiles={outcome.safe_tiles} ghosts={outcome.ghosts_eaten}"
        )
    print()
    render_evaluation(explained)
    print(f"critical moments: {tuple(int(tick) for tick in replay.critical_moments)}")
    return 0
