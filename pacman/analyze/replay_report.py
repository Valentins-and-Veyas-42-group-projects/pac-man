"""Build a tactical post-game report from recorded replay facts."""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.decision import DecisionAnalysis, analyze_decision
from pacman.analyze.event_extractor import extract_batch_events, initial_extractor_state
from pacman.analyze.events import DeathStarted, PlayerTurned
from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.models import MazeGraph
from pacman.analyze.simulation import SimulationRules
from pacman.analyze.timeline import ReplayEvaluation, summarize_replay
from pacman.replay.models import CollectibleChange, Frame, FrameBatch, Maze, ReplayId, Tick
from pacman.replay.store import ReplayStore


class ReplayReportError(Enum):
    """Failures while turning recorded facts into a tactical report."""

    DUPLICATE_FRAME_TICK = "duplicate_frame_tick"
    DECISION_FAILED = "decision_failed"
    STORE_FAILED = "store_failed"
    GRAPH_FAILED = "graph_failed"


@dataclass(frozen=True, slots=True)
class DeathReview:
    """An observed death and the latest evaluated choice before it."""

    tick: Tick
    preceding_decision: Option[DecisionAnalysis]


@dataclass(frozen=True, slots=True)
class ReplayReport:
    """Detailed turn analyses, move summary, and observed deaths."""

    decisions: tuple[DecisionAnalysis, ...]
    summary: ReplayEvaluation
    deaths: tuple[DeathReview, ...]
    unevaluated_turns: tuple[Tick, ...]


def _error(error: ReplayReportError) -> Err[ReplayReportError]:
    """Return a contextual report error.

    Returns:
        Typed report error.
    """
    return Err(error=error, namespace="replay_report", context_msg="Could not analyze replay")


def analyze_replay(
    graph: MazeGraph,
    maze: Maze,
    frames: tuple[Frame, ...],
    changes: tuple[CollectibleChange, ...],
    rules: SimulationRules,
) -> Result[ReplayReport, ReplayReportError]:
    """Evaluate observed turns and relate each death to its prior choice.

    The Python event extractor determines turns/deaths. Expensive per-turn
    searches use the selected Python, native, or WASM analysis backend.

    Returns:
        Complete post-game tactical report or a typed analysis error.
    """
    by_tick = {frame.tick: frame for frame in frames}
    if len(by_tick) != len(frames):
        return _error(ReplayReportError.DUPLICATE_FRAME_TICK)
    ordered_frames = tuple(sorted(frames, key=lambda frame: int(frame.tick)))
    previous_by_tick = {
        current.tick: previous
        for previous, current in zip(ordered_frames[:-1], ordered_frames[1:], strict=True)
    }
    batch = FrameBatch(ReplayId(0), frames, changes)
    _, events = extract_batch_events(initial_extractor_state(), batch, maze)
    decisions: list[DecisionAnalysis] = []
    deaths: list[DeathReview] = []
    unevaluated_turns: list[Tick] = []
    latest: Option[DecisionAnalysis] = Nothing()
    for event in events:
        if isinstance(event, PlayerTurned):
            frame = previous_by_tick[event.tick]
            origin = maze.tile_index(frame.player.position)
            if not graph.contains(origin) or not any(
                move.direction is event.current for move in graph.neighbors(origin)
            ):
                unevaluated_turns.append(event.tick)
                latest = Nothing()
                continue
            result = analyze_decision(graph, maze, changes, frame, event.current, rules)
            if isinstance(result, Err):
                return _error(ReplayReportError.DECISION_FAILED)
            latest = Some(result.value)
            decisions.append(result.value)
        elif isinstance(event, DeathStarted):
            deaths.append(DeathReview(event.tick, latest))
    summary = summarize_replay(tuple(decision.evaluation for decision in decisions))
    return Ok(ReplayReport(tuple(decisions), summary, tuple(deaths), tuple(unevaluated_turns)))


def analyze_saved_replay(
    store: ReplayStore,
    replay_id: ReplayId,
    rules: SimulationRules,
) -> Result[ReplayReport, ReplayReportError]:
    """Load a persisted replay and produce its complete tactical report.

    Returns:
        Post-game report or a typed storage, graph, or analysis error.
    """
    metadata = store.replay(replay_id)
    if isinstance(metadata, Err):
        return _error(ReplayReportError.STORE_FAILED)
    encoded = store.maze(metadata.value.maze_id)
    if isinstance(encoded, Err):
        return _error(ReplayReportError.STORE_FAILED)
    batch = store.batch(replay_id)
    if isinstance(batch, Err):
        return _error(ReplayReportError.STORE_FAILED)
    maze = Maze(
        id=metadata.value.maze_id,
        width=encoded.value.width,
        height=encoded.value.height,
        topology=encoded.value.topology,
        initial_collectibles=encoded.value.initial_collectibles,
        checksum=encoded.value.checksum,
    )
    graph = build_maze_graph(maze)
    if isinstance(graph, Err):
        return _error(ReplayReportError.GRAPH_FAILED)
    return analyze_replay(graph.value, maze, batch.value.frames, batch.value.collectible_changes, rules)
