"""Compare Python and native prediction on a generated mock game."""

import ctypes
import json
import subprocess
import tempfile
from argparse import ArgumentParser
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from pacman.analyze.distance_backend import AcceleratedThreatField, PredictedGhostOrigin
from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.models import MazeGraph
from pacman.analyze.native_pathfinding import PAC_OK, NativePathfinding, PacPredictedGhost, load_native_pathfinding
from pacman.analyze.prediction import _build_predicted_threat_field_python
from pacman.analyze.threat import ThreatField
from pacman.maze_loader import load_maze
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import (
    Coord,
    Direction,
    Ghost,
    GhostFrame,
    GhostState,
    Maze,
    MazeId,
    Position,
    TileIndex,
)
from typed_errs import Err, Nothing, Some

from delete_me.analyze.analysis_benchmark import encoded_graph


def measure(operation: Callable[[], object], rounds: int) -> float:
    """Return the median microseconds for one prediction operation."""
    samples: list[int] = []
    for _ in range(rounds):
        started = perf_counter_ns()
        operation()
        samples.append(perf_counter_ns() - started)
    return median(samples) / 1_000


def measure_cached_abi(
    graph: MazeGraph,
    backend: NativePathfinding,
    ghosts: tuple[PredictedGhostOrigin, ...],
    horizon: int,
    expected: AcceleratedThreatField,
    rounds: int,
) -> tuple[float, float]:
    """Time the native prediction ABI with already encoded input and output.

    Returns:
        Median microseconds for the C call and Python result decoding.

    Raises:
        RuntimeError: Native prediction failed or disagreed with its public wrapper.
    """
    topology = backend._topology_for(graph)
    if isinstance(topology, Nothing):
        raise RuntimeError("native topology unavailable")
    encoded = (PacPredictedGhost * len(ghosts))(
        *(PacPredictedGhost(int(ghost.tile), int(ghost.direction), int(ghost.ghost), int(ghost.dangerous))
          for ghost in ghosts)
    )
    count = len(graph.moves)
    etas = (ctypes.c_uint32 * count)()
    owners = (ctypes.c_uint8 * count)()

    def predict() -> None:
        status = backend._library.pac_topology_predict_threat(
            topology.value, encoded, len(ghosts), horizon, etas, owners, count,
        )
        if status != PAC_OK:
            raise RuntimeError("native prediction ABI failed")

    predict()
    if backend._decode(etas) != expected.etas or tuple(owners) != expected.owner_masks:
        raise RuntimeError("native prediction ABI differs from its public wrapper")
    abi_us = measure(predict, rounds)
    decode_us = measure(lambda: (backend._decode(etas), tuple(owners)), rounds)
    return abi_us, decode_us


def main() -> int:
    """Generate a mock game, prove equality, and print prediction timings.

    Returns:
        Zero when native prediction matches Python, otherwise one.
    """
    parser = ArgumentParser()
    parser.add_argument("--width", type=int, default=28)
    parser.add_argument("--height", type=int, default=31)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--horizon", type=int, default=12)
    parser.add_argument("--rounds", type=int, default=100)
    args = parser.parse_args()

    generated = load_maze(args.width, args.height, Some(args.seed))
    if isinstance(generated, Err):
        generated.print_diagnostic()
        return 1
    encoded = encode_topology(generated.value.cells)
    if isinstance(encoded, Err):
        encoded.print_diagnostic()
        return 1
    maze = Maze(
        MazeId(0),
        args.width,
        args.height,
        encoded.value,
        b"",
        sha256(encoded.value).digest(),
    )
    built = build_maze_graph(maze)
    loaded = load_native_pathfinding()
    if isinstance(built, Err) or isinstance(loaded, Nothing):
        print("maze graph or native library unavailable")
        return 1

    graph = built.value
    backend = loaded.value
    tile_count = len(graph.moves)
    tiles = (0, tile_count // 3, tile_count * 2 // 3, tile_count - 1)
    directions = (Direction.RIGHT, Direction.DOWN, Direction.LEFT, Direction.UP)
    ghosts = tuple(
        GhostFrame(
            Ghost(index),
            Position(Coord(tile % args.width), Coord(tile // args.width)),
            directions[index],
            GhostState.CHASE,
        )
        for index, tile in enumerate(tiles)
    )
    native_ghosts = tuple(
        PredictedGhostOrigin(
            tile=TileIndex(tile),
            direction=directions[index],
            ghost=Ghost(index),
            dangerous=True,
        )
        for index, tile in enumerate(tiles)
    )

    def python_prediction() -> ThreatField:
        return _build_predicted_threat_field_python(graph, maze, ghosts, args.horizon).unwrap()

    def native_prediction() -> AcceleratedThreatField:
        return backend.predict_threat(graph, native_ghosts, args.horizon).unwrap()

    reference = python_prediction()
    accelerated = native_prediction()
    owner_masks = tuple(sum(1 << int(ghost) for ghost in owners) for owners in reference.ghosts)
    if accelerated.etas != reference.etas or accelerated.owner_masks != owner_masks:
        print("native prediction differs from Python")
        backend.close()
        return 1

    python_us = measure(python_prediction, args.rounds)
    native_us = measure(native_prediction, args.rounds)
    abi_us, decode_us = measure_cached_abi(graph, backend, native_ghosts, args.horizon, accelerated, args.rounds)
    print(f"maze: {args.width}x{args.height}, horizon: {args.horizon}")
    print(f"{'Python prediction':22} {python_us:9.2f} us/call")
    print(f"{'C++ cached prediction':22} {native_us:9.2f} us/call")
    print(f"{'C++ ABI prediction':22} {abi_us:9.2f} us/call")
    print(f"{'C++ Python result decode':22} {decode_us:9.2f} us/call")
    print(f"{'speedup':22} {python_us / native_us:9.2f}x")
    fixture = {
        "graph": encoded_graph(graph),
        "tileCount": tile_count,
        "width": graph.width,
        "horizon": args.horizon,
        "ghosts": [[int(tile), int(directions[index]), index, 1] for index, tile in enumerate(tiles)],
        "expected": {"etas": list(reference.etas), "ownerMasks": list(owner_masks)},
    }
    with tempfile.TemporaryDirectory(prefix="pacman-prediction-") as directory:
        path = Path(directory) / "fixture.json"
        path.write_text(json.dumps(fixture), encoding="utf-8")
        completed = subprocess.run(
            ["node", "web/benchmark-prediction.mjs", str(path), str(args.rounds)],
            check=False,
        )
    backend.close()
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
