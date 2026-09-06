"""Exercise the complete analysis stack across several synthetic events."""

from dataclasses import dataclass
from enum import Enum

from pacman.analyze.collectibles import CollectibleField, reconstruct_collectibles
from pacman.analyze.evaluation import PlayEvaluation, evaluate_play
from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.models import MazeGraph
from pacman.analyze.options import ActionEvaluation, evaluate_actions
from pacman.analyze.outcomes import ActionOutcome, summarize_simulation
from pacman.analyze.prediction import GhostPrediction, build_predicted_threat_field, predict_ghost
from pacman.analyze.reasons import explain_evaluation
from pacman.analyze.simulation import SimulationRules, simulate_action
from pacman.analyze.timeline import summarize_replay
from pacman.replay.maze_codec import encode_collectibles, encode_topology
from pacman.replay.models import (
    Collectible,
    CollectibleChange,
    Coord,
    Direction,
    Frame,
    GamePhase,
    Ghost,
    GhostFrame,
    GhostState,
    Maze,
    MazeId,
    PlayerFrame,
    Position,
    Score,
    Tick,
    TileIndex,
)
from typed_errs import Err, Nothing, Ok, Option, Result, Some


class ReplayDemoError(Enum):
    """Analysis stage that rejected the synthetic replay."""

    MAZE = "maze"
    GRAPH = "graph"
    COLLECTIBLES = "collectibles"
    PREDICTION = "prediction"
    THREATS = "threats"
    OPTIONS = "options"
    SIMULATION = "simulation"
    OUTCOME = "outcome"
    EVALUATION = "evaluation"


@dataclass(frozen=True, slots=True)
class DecisionEvent:
    """One synthetic replay decision and the action Pac-Man played."""

    frame: Frame
    played_action: Direction


@dataclass(frozen=True, slots=True)
class ProcessedEvent:
    """Intermediate algorithm products retained for demo rendering."""

    event: DecisionEvent
    collectibles: CollectibleField
    predictions: tuple[GhostPrediction, ...]
    options: tuple[ActionEvaluation, ...]
    outcomes: tuple[ActionOutcome, ...]
    evaluation: PlayEvaluation


def demo_err(stage: ReplayDemoError) -> Err[ReplayDemoError]:
    """Create a replay-demo error with stage context.

    Returns:
        A contextual replay-demo error.
    """
    return Err(
        error=stage,
        namespace="replay_demo",
        context_msg=f"Synthetic replay failed during {stage.value}",
    )


def build_demo_maze() -> Result[Maze, ReplayDemoError]:
    """Build the branching maze shared by every synthetic event.

    Returns:
        The encoded maze or a typed construction error.
    """
    topology = encode_topology([[9, 5, 7], [12, 5, 7]])
    collectibles = encode_collectibles([
        Collectible.NONE,
        Collectible.POWER_PELLET,
        Collectible.NONE,
        Collectible.PACGUM,
        Collectible.PACGUM,
        Collectible.NONE,
    ])
    if isinstance(topology, Err) or isinstance(collectibles, Err):
        return demo_err(ReplayDemoError.MAZE)
    return Ok(
        Maze(
            MazeId(99),
            3,
            2,
            topology.value,
            collectibles.value,
            b"multi-event-analysis-demo",
        )
    )


def position(tile: int) -> Position:
    """Convert a demo tile index into its position.

    Returns:
        Position in the three-column demo maze.
    """
    return Position(Coord(tile % 3), Coord(tile // 3))


def event(tick: int, played: Direction) -> DecisionEvent:
    """Build one decision with a lethal and a frightened ghost route.

    Returns:
        Synthetic replay decision.
    """
    return DecisionEvent(
        Frame(
            Tick(tick),
            PlayerFrame(position(0), played),
            (
                GhostFrame(Ghost.BLINKY, position(2), Direction.LEFT, GhostState.CHASE),
                GhostFrame(
                    Ghost.PINKY,
                    position(5),
                    Direction.LEFT,
                    GhostState.FRIGHTENED,
                ),
            ),
            Score(0),
            3,
            GamePhase.PLAYING,
        ),
        played,
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


def process_event(
    graph: MazeGraph,
    maze: Maze,
    changes: tuple[CollectibleChange, ...],
    decision: DecisionEvent,
    rules: SimulationRules,
) -> Result[ProcessedEvent, ReplayDemoError]:
    """Run one decision through every analysis algorithm stage.

    Returns:
        All intermediate products or the stage that failed.
    """
    collectible_field = reconstruct_collectibles(maze, changes, decision.frame.tick)
    if isinstance(collectible_field, Err):
        return demo_err(ReplayDemoError.COLLECTIBLES)

    predictions: list[GhostPrediction] = []
    for ghost in decision.frame.ghosts:
        prediction = predict_ghost(graph, maze, ghost, rules.horizon_ticks)
        if isinstance(prediction, Err):
            return demo_err(ReplayDemoError.PREDICTION)
        predictions.append(prediction.value)

    threat_field = build_predicted_threat_field(
        graph,
        maze,
        decision.frame.ghosts,
        rules.horizon_ticks,
    )
    if isinstance(threat_field, Err):
        return demo_err(ReplayDemoError.THREATS)
    player_tile = maze.tile_index(decision.frame.player.position)
    options = evaluate_actions(graph, threat_field.value, player_tile)
    if isinstance(options, Err):
        return demo_err(ReplayDemoError.OPTIONS)

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
            return demo_err(ReplayDemoError.SIMULATION)
        outcome = summarize_simulation(
            simulation.value,
            option_for(options.value, move.direction),
        )
        if isinstance(outcome, Err):
            return demo_err(ReplayDemoError.OUTCOME)
        outcomes.append(outcome.value)

    evaluation = evaluate_play(
        decision.frame.tick,
        decision.played_action,
        tuple(outcomes),
    )
    if isinstance(evaluation, Err):
        return demo_err(ReplayDemoError.EVALUATION)
    return Ok(
        ProcessedEvent(
            decision,
            collectible_field.value,
            tuple(predictions),
            options.value,
            tuple(outcomes),
            explain_evaluation(evaluation.value),
        )
    )


def run() -> int:
    """Process multiple synthetic events and render their replay summary.

    Returns:
        Zero on success or one when a stage rejects an event.
    """
    maze = build_demo_maze()
    if isinstance(maze, Err):
        maze.print_diagnostic()
        return 1
    graph = build_maze_graph(maze.value)
    if isinstance(graph, Err):
        demo_err(ReplayDemoError.GRAPH).print_diagnostic()
        return 1

    changes = (
        CollectibleChange(Tick(150), TileIndex(1), Collectible.NONE),
        CollectibleChange(Tick(250), TileIndex(3), Collectible.NONE),
        CollectibleChange(Tick(250), TileIndex(4), Collectible.NONE),
    )
    decisions = (
        event(100, Direction.RIGHT),
        event(200, Direction.RIGHT),
        event(300, Direction.DOWN),
    )
    rules = SimulationRules(horizon_ticks=3)
    processed: list[ProcessedEvent] = []
    for decision in decisions:
        result = process_event(graph.value, maze.value, changes, decision, rules)
        if isinstance(result, Err):
            result.print_diagnostic()
            return 1
        processed.append(result.value)

    print("multi-event replay analysis")
    for result in processed:
        remaining = sum(value is not Collectible.NONE for value in result.collectibles.tiles)
        evaluation = result.evaluation
        print()
        print(
            f"tick {int(evaluation.tick)} played={evaluation.played.action.name} "
            f"best={evaluation.best.action.name} quality={evaluation.quality.value}"
        )
        print(
            f"  reconstructed collectibles={remaining} "
            f"ghost predictions={len(result.predictions)} options={len(result.options)}"
        )
        for outcome in result.outcomes:
            print(
                f"  {outcome.action.name:<5} died={str(outcome.died):<5} "
                f"score={outcome.score_gained:<4} ghosts={outcome.ghosts_eaten} "
                f"safe_tiles={outcome.safe_tiles}"
            )
        print("  reasons=" + ", ".join(reason.value for reason in evaluation.reasons))

    summary = summarize_replay(tuple(result.evaluation for result in processed))
    print()
    print("replay summary")
    print(
        f"  best={summary.best_moves} good={summary.good_moves} "
        f"inaccuracies={summary.inaccuracies} mistakes={summary.mistakes} "
        f"blunders={summary.blunders}"
    )
    print(f"  critical={tuple(int(tick) for tick in summary.critical_moments)}")
    return 0
