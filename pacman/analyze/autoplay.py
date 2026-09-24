"""Choose a provisional safe direction from one observed replay frame."""

from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.decision import analyze_decision
from pacman.analyze.models import MazeGraph
from pacman.analyze.options import ActionEvaluation, evaluate_actions
from pacman.analyze.outcomes import best_outcome
from pacman.analyze.prediction import build_predicted_threat_field
from pacman.analyze.simulation import SimulationRules
from pacman.replay.models import CollectibleChange, Direction, Frame, Maze


class AutoPlayError(Enum):
    """Stages that can reject a decision request."""

    INVALID_FRAME = "invalid_frame"
    PREDICTION_FAILED = "prediction_failed"
    OPTIONS_FAILED = "options_failed"
    ANALYSIS_FAILED = "analysis_failed"


def _error(error: AutoPlayError) -> Err[AutoPlayError]:
    """Return a contextual decision error.

    Returns:
        Typed error for the failed analysis stage.
    """
    return Err(error=error, namespace="autoplay", context_msg="Could not choose a player action")


def _rank(action: ActionEvaluation) -> tuple[int, int, int, int]:
    """Order legal moves by safe territory and escape routes.

    Returns:
        A tuple whose larger values are preferable.
    """
    return (
        action.safe_tiles,
        action.safe_intersections,
        action.horizon_ticks,
        action.minimum_margin.unwrap_or(0),
    )


def choose_action(
    graph: MazeGraph, maze: Maze, frame: Frame, horizon: int = 12
) -> Result[Option[Direction], AutoPlayError]:
    """Predict ghosts and select a move by safe reachability.

    This does not run the branch simulator or optimize collectible score.

    Returns:
        The best legal direction, Nothing at a tile with no exits, or a typed error.
    """
    player_tile = maze.tile_index(frame.player.position)
    if not graph.contains(player_tile):
        return _error(AutoPlayError.INVALID_FRAME)
    threats = build_predicted_threat_field(graph, maze, frame.ghosts, horizon)
    if isinstance(threats, Err):
        return _error(AutoPlayError.PREDICTION_FAILED)
    actions = evaluate_actions(graph, threats.value, player_tile)
    if isinstance(actions, Err):
        return _error(AutoPlayError.OPTIONS_FAILED)
    if not actions.value:
        return Ok(Nothing())
    return Ok(Some(max(actions.value, key=_rank).action))


def choose_tactical_action(
    graph: MazeGraph,
    maze: Maze,
    changes: tuple[CollectibleChange, ...],
    frame: Frame,
    rules: SimulationRules,
) -> Result[Option[Direction], AutoPlayError]:
    """Choose the best bounded counterfactual, including score and survival.

    This is an analysis policy, not a game-loop or input adapter. It uses the
    same backend-selected computation as replay decision analysis.

    Returns:
        Best legal direction, Nothing at a tile with no exits, or a typed error.
    """
    origin = maze.tile_index(frame.player.position)
    if not graph.contains(origin):
        return _error(AutoPlayError.INVALID_FRAME)
    moves = graph.neighbors(origin)
    if not moves:
        return Ok(Nothing())
    analyzed = analyze_decision(
        graph, maze, changes, frame, moves[0].direction, rules,
    )
    if isinstance(analyzed, Err):
        return _error(AutoPlayError.ANALYSIS_FAILED)
    best = best_outcome(analyzed.value.outcomes)
    if isinstance(best, Nothing):
        return Ok(Nothing())
    return Ok(Some(best.value.action))
