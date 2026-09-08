"""Compose tactical analysis primitives for one observed player decision."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.collectibles import CollectibleField, reconstruct_collectibles
from pacman.analyze.evaluation import PlayEvaluation, evaluate_play
from pacman.analyze.models import MazeGraph
from pacman.analyze.options import ActionEvaluation, evaluate_actions
from pacman.analyze.outcomes import ActionOutcome, summarize_simulation
from pacman.analyze.prediction import GhostPrediction, build_predicted_threat_field, predict_ghost
from pacman.analyze.reasons import explain_evaluation
from pacman.analyze.simulation import SimulationRules, simulate_action
from pacman.replay.models import CollectibleChange, Direction, Frame, Maze


class DecisionAnalysisError(Enum):
    """Stage that rejected an observed replay decision."""

    COLLECTIBLES = "collectibles"
    PREDICTION = "prediction"
    THREATS = "threats"
    OPTIONS = "options"
    SIMULATION = "simulation"
    OUTCOME = "outcome"
    EVALUATION = "evaluation"


@dataclass(frozen=True, slots=True)
class DecisionAnalysis:
    """Intermediate and final products for one observed decision."""

    frame: Frame
    played_action: Direction
    collectibles: CollectibleField
    predictions: tuple[GhostPrediction, ...]
    options: tuple[ActionEvaluation, ...]
    outcomes: tuple[ActionOutcome, ...]
    evaluation: PlayEvaluation


def decision_err(stage: DecisionAnalysisError) -> Err[DecisionAnalysisError]:
    """Create a contextual decision-analysis error.

    Returns:
        Typed error identifying the failed analysis stage.
    """
    return Err(
        error=stage,
        namespace="decision_analysis",
        context_msg=f"Replay decision failed during {stage.value}",
    )


def option_for(
    options: tuple[ActionEvaluation, ...],
    direction: Direction,
) -> Option[ActionEvaluation]:
    """Find cheap safety facts for an action.

    Returns:
        Matching action facts or ``Nothing``.
    """
    for option in options:
        if option.action is direction:
            return Some(option)
    return Nothing()


def analyze_decision(
    graph: MazeGraph,
    maze: Maze,
    changes: tuple[CollectibleChange, ...],
    frame: Frame,
    played_action: Direction,
    rules: SimulationRules,
) -> Result[DecisionAnalysis, DecisionAnalysisError]:
    """Evaluate one recorded choice against bounded alternatives.

    Returns:
        Composed tactical analysis or the stage that failed.
    """
    collectible_field = reconstruct_collectibles(maze, changes, frame.tick)
    if isinstance(collectible_field, Err):
        return decision_err(DecisionAnalysisError.COLLECTIBLES)

    predictions: list[GhostPrediction] = []
    for ghost in frame.ghosts:
        prediction = predict_ghost(graph, maze, ghost, rules.horizon_ticks)
        if isinstance(prediction, Err):
            return decision_err(DecisionAnalysisError.PREDICTION)
        predictions.append(prediction.value)

    threat_field = build_predicted_threat_field(
        graph,
        maze,
        frame.ghosts,
        rules.horizon_ticks,
    )
    if isinstance(threat_field, Err):
        return decision_err(DecisionAnalysisError.THREATS)
    player_tile = maze.tile_index(frame.player.position)
    options = evaluate_actions(graph, threat_field.value, player_tile)
    if isinstance(options, Err):
        return decision_err(DecisionAnalysisError.OPTIONS)

    outcomes: list[ActionOutcome] = []
    for move in graph.neighbors(player_tile):
        simulation = simulate_action(
            graph,
            collectible_field.value,
            tuple(predictions),
            player_tile,
            move.direction,
            rules,
        )
        if isinstance(simulation, Err):
            return decision_err(DecisionAnalysisError.SIMULATION)
        outcome = summarize_simulation(
            simulation.value,
            option_for(options.value, move.direction),
        )
        if isinstance(outcome, Err):
            return decision_err(DecisionAnalysisError.OUTCOME)
        outcomes.append(outcome.value)

    evaluation = evaluate_play(frame.tick, played_action, tuple(outcomes))
    if isinstance(evaluation, Err):
        return decision_err(DecisionAnalysisError.EVALUATION)
    return Ok(
        DecisionAnalysis(
            frame,
            played_action,
            collectible_field.value,
            tuple(predictions),
            options.value,
            tuple(outcomes),
            explain_evaluation(evaluation.value),
        )
    )
