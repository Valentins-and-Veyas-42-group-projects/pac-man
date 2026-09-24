"""Time the same FakeGame safety decisions in Python, native C++, and WASM."""

import json
import os
import subprocess
import tempfile
from argparse import ArgumentParser
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter_ns
from typing import TypedDict

from pacman.analyze.collectibles import reconstruct_collectibles
from pacman.analyze.decision import analyze_decision
from pacman.analyze.distance_backend import (
    DistanceBackendKind,
    active_distance_backend,
    close_distance_backend,
)
from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.models import MazeGraph
from pacman.analyze.options import ActionEvaluation, evaluate_actions
from pacman.analyze.outcomes import terminal_rank
from pacman.analyze.prediction import build_predicted_threat_field, predict_ghost
from pacman.analyze.simulation import SimulationRules, simulate_action
from pacman.analyze.simulation_bridge import prepare_simulation
from pacman.maze_loader import load_maze
from pacman.replay.maze_codec import encode_collectibles, encode_topology
from pacman.replay.models import (
    Collectible,
    CollectibleChange,
    Coord,
    Direction,
    Frame,
    Ghost,
    GhostFrame,
    GhostState,
    Maze,
    MazeId,
    Position,
    ReplayId,
    TileIndex,
)
from typed_errs import Some

from delete_me.analyze.pipeline_main import TICK_HZ, FakeGame

TILE_SIZE = 18
SAMPLE_EVERY_TICKS = 30


class Snapshot(TypedDict):
    """One sampled FakeGame state shared with the WASM worker."""

    playerTile: int  # noqa: N815
    ghosts: list[list[int]]


def encoded_graph(graph: MazeGraph) -> list[int]:
    """Flatten maze moves for the WASM worker.

    Returns:
        Bytes matching the C ABI graph layout.
    """
    encoded = bytearray(len(graph.moves) * TILE_SIZE)
    for tile, moves in enumerate(graph.moves):
        for index, move in enumerate(moves):
            offset = tile * TILE_SIZE + index * 4
            destination = int(move.destination)
            encoded[offset] = destination & 0xFF
            encoded[offset + 1] = destination >> 8
            encoded[offset + 2] = int(move.direction)
            encoded[offset + 3] = int(move.wraparound)
        encoded[tile * TILE_SIZE + 16] = len(moves)
    return list(encoded)


def generate_case(
    width: int, height: int, seed: int, seconds: int
) -> tuple[Maze, MazeGraph, list[Snapshot], tuple[Frame, ...], tuple[CollectibleChange, ...]]:
    """Run the existing FakeGame and sample its actual observed states.

    Returns:
        Maze, graph, and deterministic tactical snapshots.
    """
    generated = load_maze(width, height, Some(seed)).unwrap()
    topology = encode_topology(generated.cells).unwrap()
    setup_rng = Random(seed)
    collectibles = [
        Collectible.POWER_PELLET if setup_rng.random() < 0.06 else Collectible.PACGUM for _ in range(width * height)
    ]
    entry = generated.entry[1] * width + generated.entry[0]
    collectibles[entry] = Collectible.NONE
    initial_collectibles = encode_collectibles(collectibles).unwrap()
    maze = Maze(MazeId(1), width, height, topology, initial_collectibles, b"analysis-benchmark")
    graph = build_maze_graph(maze).unwrap()
    last = len(graph.moves) - 1
    game = FakeGame(
        ReplayId(1),
        maze,
        graph,
        Random(seed),
        0.08,
        TileIndex(entry),
        {ghost: TileIndex(max(0, last - int(ghost) * 3)) for ghost in Ghost},
        collectibles,
        tuple(collectibles),
    )
    snapshots: list[Snapshot] = []
    sampled_frames: list[Frame] = []
    changes: list[CollectibleChange] = []
    for tick in range(seconds * TICK_HZ):
        step = game.step(tick)
        frame = step.frame
        if isinstance(step.collectible_change, Some):
            changes.append(step.collectible_change.value)
        if tick % SAMPLE_EVERY_TICKS != 0:
            continue
        sampled_frames.append(frame)
        snapshots.append({
            "playerTile": int(maze.tile_index(frame.player.position)),
            "ghosts": [
                [
                    int(maze.tile_index(ghost.position)),
                    int(ghost.direction),
                    int(ghost.ghost),
                    int(ghost.state not in (GhostState.FRIGHTENED, GhostState.EATEN)),
                ]
                for ghost in frame.ghosts
            ],
        })
    return maze, graph, snapshots, tuple(sampled_frames), tuple(changes)


def _action_values(action: ActionEvaluation) -> list[object]:
    """Return only semantic action facts shared by all three backends.

    Returns:
        Stable JSON-compatible values.
    """
    return [
        int(action.action),
        int(action.first_tile),
        [int(tile) for tile in action.reachable_tiles],
        action.safe_tiles,
        action.safe_intersections,
        action.horizon_ticks,
        action.minimum_margin.value if isinstance(action.minimum_margin, Some) else None,
    ]


def analyze_snapshot(maze: Maze, graph: MazeGraph, snapshot: Snapshot, horizon: int) -> list[object]:
    """Run the production prediction and action-evaluation entry points.

    Returns:
        Predicted danger arrivals and legal-action facts.
    """
    ghosts = tuple(
        GhostFrame(
            Ghost(record[2]),
            Position(Coord(record[0] % maze.width), Coord(record[0] // maze.width)),
            Direction(record[1]),
            GhostState.CHASE if record[3] else GhostState.FRIGHTENED,
        )
        for record in snapshot["ghosts"]
    )
    player_tile = TileIndex(snapshot["playerTile"])
    field = build_predicted_threat_field(graph, maze, ghosts, horizon).unwrap()
    actions = evaluate_actions(graph, field, player_tile).unwrap()
    return [list(field.etas), [_action_values(action) for action in actions]]


def simulation_cases(
    maze: Maze,
    graph: MazeGraph,
    frames: tuple[Frame, ...],
    changes: tuple[CollectibleChange, ...],
    rules: SimulationRules,
) -> list[dict[str, object]]:
    """Capture exact Python branches for native/WASM parity checks.

    Returns:
        Flat worker inputs and Python reference terminal summaries.
    """
    cases: list[dict[str, object]] = []
    for frame in frames:
        origin = maze.tile_index(frame.player.position)
        collectibles = reconstruct_collectibles(maze, changes, frame.tick).unwrap()
        predictions = tuple(predict_ghost(graph, maze, ghost, rules.horizon_ticks).unwrap() for ghost in frame.ghosts)
        prepared = prepare_simulation(collectibles, predictions, origin, rules).unwrap()
        for move in graph.neighbors(origin):
            reference = simulate_action(
                graph,
                collectibles,
                predictions,
                origin,
                move.direction,
                rules,
            ).unwrap()
            best = max(reference.terminals, key=terminal_rank)
            cases.append({
                "collectibles": list(prepared.collectibles),
                "predictionGrid": list(prepared.prediction_grid),
                "ghostOrder": list(prepared.ghost_order),
                "origin": int(origin),
                "action": int(move.direction),
                "horizon": rules.horizon_ticks,
                "pacgumScore": rules.pacgum_score,
                "powerPelletScore": rules.power_pellet_score,
                "frightenedTicks": rules.frightened_ticks,
                "comboScores": list(rules.ghost_combo_scores),
                "expected": [
                    best.score_gained,
                    best.tick,
                    best.pacgums_eaten,
                    best.power_pellets_eaten,
                    len(best.eaten_ghosts),
                    best.frightened_remaining,
                    best.died,
                    [int(tile) for tile in best.path],
                ],
            })
    return cases


def measure(operation: Callable[[], object], rounds: int, count: int) -> float:
    """Return median microseconds per snapshot over complete rounds.

    Returns:
        Time per analyzed FakeGame snapshot.
    """
    samples: list[float] = []
    for _ in range(rounds):
        started = perf_counter_ns()
        operation()
        samples.append((perf_counter_ns() - started) / count / 1_000)
    return median(samples)


def main() -> int:
    """Verify equal outputs and report safety-analysis timings.

    Returns:
        Zero on agreement, otherwise one.
    """
    parser = ArgumentParser()
    parser.add_argument("--width", type=int, default=28)
    parser.add_argument("--height", type=int, default=31)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--horizon", type=int, default=12)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--decision-samples", type=int, default=3)
    parser.add_argument("--decision-rounds", type=int, default=2)
    args = parser.parse_args()
    if min(args.seconds, args.rounds, args.decision_samples, args.decision_rounds) <= 0 or args.horizon < 0:
        print("seconds, rounds, and samples must be positive; horizon must be nonnegative")
        return 2

    maze, graph, snapshots, frames, changes = generate_case(args.width, args.height, args.seed, args.seconds)
    decision_frames = frames[: args.decision_samples]
    decision_rules = SimulationRules(horizon_ticks=4)
    previous_backend = os.environ.get("PACMAN_ANALYSIS_BACKEND")
    previous_library = os.environ.get("PACMAN_NATIVE_LIBRARY")
    try:
        shown = subprocess.run(
            ["xmake", "show", "-t", "pacman-native", "--format=json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if shown.returncode != 0:
            print("xmake could not report the release native library")
            return 1
        target = json.loads(shown.stdout)["targetfile"]
        os.environ["PACMAN_NATIVE_LIBRARY"] = str(Path(target).resolve())
    except (OSError, ValueError, KeyError) as error:
        print(f"could not find native library: {error}")
        return 1
    timings: dict[str, float] = {}
    decision_timings: dict[str, float] = {}
    expected: list[list[object]] | None = None
    expected_decisions: tuple[object, ...] | None = None
    try:
        for mode, kind in (("python", DistanceBackendKind.PYTHON), ("native", DistanceBackendKind.NATIVE)):
            close_distance_backend()
            os.environ["PACMAN_ANALYSIS_BACKEND"] = mode
            if active_distance_backend() is not kind:
                print(f"{mode} backend unavailable; comparison aborted")
                return 1

            def run_all() -> list[list[object]]:
                return [analyze_snapshot(maze, graph, item, args.horizon) for item in snapshots]

            actual = run_all()
            if expected is None:
                expected = actual
            elif actual != expected:
                print(f"{mode} output differs from Python")
                return 1
            timings[mode] = measure(run_all, args.rounds, len(snapshots))

            def run_decisions() -> tuple[object, ...]:
                return tuple(
                    analyze_decision(
                        graph,
                        maze,
                        changes,
                        frame,
                        graph.neighbors(maze.tile_index(frame.player.position))[0].direction,
                        decision_rules,
                    ).unwrap()
                    for frame in decision_frames
                )

            decisions = run_decisions()
            if expected_decisions is None:
                expected_decisions = decisions
            elif decisions != expected_decisions:
                print(f"{mode} full decision output differs from Python")
                return 1
            decision_timings[mode] = measure(run_decisions, args.decision_rounds, len(decision_frames))
    finally:
        close_distance_backend()
        if previous_backend is None:
            os.environ.pop("PACMAN_ANALYSIS_BACKEND", None)
        else:
            os.environ["PACMAN_ANALYSIS_BACKEND"] = previous_backend
        if previous_library is None:
            os.environ.pop("PACMAN_NATIVE_LIBRARY", None)
        else:
            os.environ["PACMAN_NATIVE_LIBRARY"] = previous_library

    assert expected is not None
    digest = sha256(json.dumps(expected, separators=(",", ":")).encode()).hexdigest()
    fixture = {
        "graph": encoded_graph(graph),
        "tileCount": len(graph.moves),
        "width": graph.width,
        "horizon": args.horizon,
        "snapshots": snapshots,
        "simulationCases": simulation_cases(
            maze,
            graph,
            decision_frames,
            changes,
            decision_rules,
        ),
    }
    print(f"FakeGame: {args.width}x{args.height}, {args.seconds}s, {len(snapshots)} sampled states", flush=True)
    print("Prediction + safe-action evaluation, median us/state (game generation excluded):", flush=True)
    print(f"  Python reference     {timings['python']:9.2f}", flush=True)
    print(f"  Native C++ via Python {timings['native']:9.2f}  {timings['python'] / timings['native']:.2f}x", flush=True)
    with tempfile.TemporaryDirectory(prefix="pacman-analysis-") as directory:
        path = Path(directory) / "fixture.json"
        try:
            path.write_text(json.dumps(fixture), encoding="utf-8")
        except OSError as error:
            print(f"could not write temporary benchmark fixture: {error}")
            return 1
        command = [
            "node",
            "web/benchmark-analysis-worker.mjs",
            str(path),
            str(args.rounds),
            digest,
            str(timings["python"]),
        ]
        print("WASM worker check: node web/benchmark-analysis-worker.mjs <temporary fixture>", flush=True)
        try:
            completed = subprocess.run(command, check=False)
        except OSError as error:
            print(f"could not start Node: {error}")
            return 1
        if completed.returncode != 0:
            return completed.returncode
    print(f"Full analyze_decision(), {len(decision_frames)} states, median us/decision:")
    print(f"  Python reference     {decision_timings['python']:9.2f}")
    decision_speedup = decision_timings["python"] / decision_timings["native"]
    print(f"  Native C++ via Python {decision_timings['native']:9.2f}  {decision_speedup:.2f}x")
    print(
        "  WASM branch search matches Python above; browser replay orchestration is not yet verified"
    )
    print("WASM timing includes Node worker IPC; native timing includes Python/ctypes conversion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
