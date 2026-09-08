"""Load the latest persisted replay and run tactical analysis over it."""

from dataclasses import replace

from pacman.analyze.decision import analyze_decision
from pacman.analyze.evaluation import PlayQuality
from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.models import MazeGraph
from pacman.analyze.simulation import SimulationRules
from pacman.analyze.timeline import evaluation_loss, summarize_replay
from pacman.analyze.topology import TileKind, classify_tile
from pacman.replay.models import Frame, GamePhase, GhostState, Maze, Tick, TileIndex
from pacman.replay.store import ReplayStore
from typed_errs import Err, Some

from delete_me.analyze.pipeline_main import DB_PATH

DEATH_CONTEXT_TICKS = 120
MAX_CAUSE_SEARCH_TICKS = 600


def pressured(frame: Frame, maximum_distance: int = 4) -> bool:
    """Return whether a dangerous ghost is locally close to Pac-Man."""
    player = frame.player.position
    return any(
        ghost.state not in (GhostState.FRIGHTENED, GhostState.EATEN)
        and abs(int(ghost.position.x) - int(player.x)) + abs(int(ghost.position.y) - int(player.y)) <= maximum_distance
        for ghost in frame.ghosts
    )


def near_tick(tick: Tick, targets: tuple[Tick, ...], radius: int) -> bool:
    """Return whether a tick falls inside a noteworthy context window."""
    return any(abs(int(tick) - int(target)) <= radius for target in targets)


def decision_boundary(
    previous: Frame,
    current: Frame,
    maze: Maze,
    graph: MazeGraph,
) -> bool:
    """Return whether a transition represents a junction decision."""
    if previous.player.direction is current.player.direction:
        return False
    kind = classify_tile(graph, maze.tile_index(previous.player.position))
    return isinstance(kind, Some) and kind.value is TileKind.INTERSECTION


def root_cause_range(
    tick: Tick,
    frames: tuple[Frame, ...],
    maze: Maze,
    graph: MazeGraph,
) -> tuple[Tick, Tick]:
    """Infer the setup-to-consequence window around one bad decision.

    Returns:
        Start and end ticks bounded by tactical state changes.
    """
    index = min(max(int(tick), 0), len(frames) - 1)
    start = index
    end = index
    under_pressure = pressured(frames[index])

    if under_pressure:
        while start > 0 and int(tick) - int(frames[start - 1].tick) <= MAX_CAUSE_SEARCH_TICKS:
            if not pressured(frames[start - 1]):
                break
            start -= 1
    else:
        cursor = index
        while cursor > 0 and int(tick) - int(frames[cursor - 1].tick) <= MAX_CAUSE_SEARCH_TICKS:
            if decision_boundary(frames[cursor - 1], frames[cursor], maze, graph):
                start = cursor
                break
            cursor -= 1

    cursor = index + 1
    while cursor < len(frames) and int(frames[cursor].tick) - int(tick) <= MAX_CAUSE_SEARCH_TICKS:
        end = cursor
        if frames[cursor].phase is GamePhase.DYING:
            break
        if under_pressure and not pressured(frames[cursor]):
            break
        if decision_boundary(frames[cursor - 1], frames[cursor], maze, graph):
            break
        cursor += 1
    return frames[start].tick, frames[end].tick


def run(limit: int = 5) -> int:
    """Analyze decisions from the latest generated replay.

    Returns:
        Zero after analysis, or one with a generation hint when data is absent.
    """
    if limit <= 0:
        print("analysis-limit must be positive")
        return 2
    if not DB_PATH.exists():
        print("no generated replay found")
        print("run this first: uv run python -m delete_me.analyze.main --case pipeline")
        return 1

    store = ReplayStore(DB_PATH)
    replay_id = store.latest_replay_id()
    if isinstance(replay_id, Err):
        print("the replay database contains no analyzable run")
        print("run this first: uv run python -m delete_me.analyze.main --case pipeline")
        return 1
    metadata = store.replay(replay_id.value)
    batch = store.batch(replay_id.value)
    if isinstance(metadata, Err) or isinstance(batch, Err):
        print("failed to reconstruct the latest replay")
        return 1
    encoded = store.maze(metadata.value.maze_id)
    if isinstance(encoded, Err):
        encoded.print_diagnostic()
        return 1
    maze = Maze(
        metadata.value.maze_id,
        encoded.value.width,
        encoded.value.height,
        encoded.value.topology,
        encoded.value.initial_collectibles,
        encoded.value.checksum,
    )
    graph = build_maze_graph(maze)
    if isinstance(graph, Err):
        graph.print_diagnostic()
        return 1

    topology_counts = {kind: 0 for kind in TileKind}
    for raw_tile in range(len(graph.value.moves)):
        kind = classify_tile(graph.value, TileIndex(raw_tile))
        if isinstance(kind, Some):
            topology_counts[kind.value] += 1

    evaluations = []
    skipped = 0
    ignored = 0
    frames = batch.value.frames
    death_ticks = tuple(frame.tick for frame in frames if frame.phase is GamePhase.DYING)
    for previous, current in zip(frames, frames[1:], strict=False):
        if previous.player.direction is current.player.direction:
            continue
        player_tile = maze.tile_index(previous.player.position)
        tile_kind = classify_tile(graph.value, player_tile)
        at_junction = isinstance(tile_kind, Some) and tile_kind.value is TileKind.INTERSECTION
        if not (at_junction or pressured(previous) or near_tick(current.tick, death_ticks, DEATH_CONTEXT_TICKS)):
            ignored += 1
            continue
        processed = analyze_decision(
            graph.value,
            maze,
            batch.value.collectible_changes,
            replace(previous, tick=current.tick),
            current.player.direction,
            SimulationRules(horizon_ticks=4),
        )
        if isinstance(processed, Err):
            skipped += 1
            continue
        evaluations.append(processed.value.evaluation)

    summary = summarize_replay(tuple(evaluations), critical_limit=limit)
    grouped = {
        quality: tuple(
            sorted(
                (evaluation for evaluation in summary.decisions if evaluation.quality is quality),
                key=evaluation_loss,
                reverse=True,
            )[:limit]
        )
        for quality in (
            PlayQuality.BLUNDER,
            PlayQuality.MISTAKE,
            PlayQuality.INACCURACY,
        )
    }

    print("== latest persisted replay analysis ==")
    print(f"replay:      {int(replay_id.value)}")
    print(f"maze:        {maze.width}x{maze.height}")
    print("topology:    " + ", ".join(f"{kind.value}={topology_counts[kind]}" for kind in TileKind))
    print(f"frames:      {len(frames):,}")
    print(f"noteworthy:  {len(summary.decisions):,} analyzed, {ignored:,} ordinary turns ignored, {skipped} invalid")
    print(f"errors:      inaccuracies={summary.inaccuracies} mistakes={summary.mistakes} blunders={summary.blunders}")
    print(f"deaths:      {tuple(int(tick) for tick in death_ticks)}")
    labels = {
        PlayQuality.BLUNDER: "blunders",
        PlayQuality.MISTAKE: "mistakes",
        PlayQuality.INACCURACY: "inaccuracies",
    }
    for quality in (PlayQuality.BLUNDER, PlayQuality.MISTAKE, PlayQuality.INACCURACY):
        print(f"\nworst {labels[quality]}:")
        if not grouped[quality]:
            print("  none detected")
            continue
        for evaluation in grouped[quality]:
            reasons = ", ".join(reason.value for reason in evaluation.reasons)
            start, end = root_cause_range(evaluation.tick, frames, maze, graph.value)
            print(
                f"  tick {int(evaluation.tick):>5} cause={int(start)}..{int(end)} "
                f"played={evaluation.played.action.name:<5} "
                f"best={evaluation.best.action.name:<5} reasons={reasons}"
            )
    return 0
