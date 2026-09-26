"""Compare Python and native BFS implementations on a generated maze."""

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

from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.models import MazeGraph
from pacman.analyze.native_pathfinding import PAC_OK, NativePathfinding, load_native_pathfinding
from pacman.analyze.pathfinding import bfs
from pacman.maze_loader import load_maze
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import Maze, MazeId, TileIndex
from typed_errs import Err, Nothing, Some

from delete_me.analyze.analysis_benchmark import encoded_graph

Search = Callable[[MazeGraph, TileIndex], tuple[int, ...]]


def measure(graph: MazeGraph, search: Search, rounds: int) -> float:
    """Return median nanoseconds per origin across complete-maze rounds."""
    samples: list[float] = []
    origins = tuple(TileIndex(index) for index in range(len(graph.moves)))
    for _ in range(rounds):
        started = perf_counter_ns()
        for origin in origins:
            search(graph, origin)
        samples.append((perf_counter_ns() - started) / len(origins))
    return median(samples)


def measure_batch(graph: MazeGraph, backend: NativePathfinding, rounds: int) -> float:
    """Return median nanoseconds per field using five-origin batches.

    Raises:
        RuntimeError: Native batch execution failed.
    """
    origins = tuple(TileIndex(index) for index in range(len(graph.moves)))
    batches = tuple(origins[index : index + 5] for index in range(0, len(origins), 5))
    samples: list[float] = []
    for _ in range(rounds):
        started = perf_counter_ns()
        for batch in batches:
            if isinstance(backend.distances_many(graph, batch), Nothing):
                raise RuntimeError("native batch BFS failed")
        samples.append((perf_counter_ns() - started) / len(origins))
    return median(samples)


def measure_cached_abi(graph: MazeGraph, backend: NativePathfinding, rounds: int) -> tuple[float, float]:
    """Time the cached C ABI with reusable storage to expose wrapper cost.

    Returns:
        Median nanoseconds for the C call and for Python distance decoding.

    Raises:
        RuntimeError: Topology creation or a native lookup failed.
    """
    topology = backend._topology_for(graph)
    if isinstance(topology, Nothing):
        raise RuntimeError("native topology unavailable")
    count = len(graph.moves)
    output = (ctypes.c_uint32 * count)()
    search = backend._library.pac_topology_bfs_distances
    if search(topology.value, 0, output, count) != PAC_OK:
        raise RuntimeError("native cached lookup failed")
    samples: list[float] = []
    for _ in range(rounds):
        started = perf_counter_ns()
        for origin in range(count):
            if search(topology.value, origin, output, count) != PAC_OK:
                raise RuntimeError(f"native cached lookup failed at origin {origin}")
        samples.append((perf_counter_ns() - started) / count)
    decode_samples: list[float] = []
    for _ in range(rounds):
        started = perf_counter_ns()
        for _ in range(count):
            backend._decode(output)
        decode_samples.append((perf_counter_ns() - started) / count)
    return median(samples), median(decode_samples)


def measure_graph_encoding(graph: MazeGraph, backend: NativePathfinding, rounds: int) -> float:
    """Expose the Python graph conversion included in native one-shot calls.

    Returns:
        Median nanoseconds per graph encoding.

    Raises:
        RuntimeError: The graph could not be encoded for the C ABI.
    """
    count = len(graph.moves)
    samples: list[float] = []
    for _ in range(rounds):
        started = perf_counter_ns()
        for _ in range(count):
            if isinstance(backend._encode(graph), Nothing):
                raise RuntimeError("native graph encoding failed")
        samples.append((perf_counter_ns() - started) / count)
    return median(samples)


def native_search(backend: NativePathfinding, mode: str) -> Search:
    """Create a callable for cached, graph, or one-shot masked native BFS.

    Returns:
        A uniform search callable for the selected native mode.
    """

    def search(graph: MazeGraph, origin: TileIndex) -> tuple[int, ...]:
        if mode == "selected":
            result = backend.distances(graph, origin)
        elif mode == "graph-cached":
            result = backend.cached_distances(graph, origin, masked=False)
        elif mode == "masked-cached":
            result = backend.cached_distances(graph, origin, masked=True)
        else:
            result = backend.one_shot_distances(graph, origin, masked=mode == "masked-one-shot")
        if isinstance(result, Nothing):
            raise RuntimeError("native BFS failed")
        return result.value

    return search


def main() -> int:
    """Generate a maze, prove equality, and print comparable timings.

    Returns:
        Zero when every implementation agrees, otherwise one.
    """
    parser = ArgumentParser()
    parser.add_argument("--width", type=int, default=28)
    parser.add_argument("--height", type=int, default=31)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rounds", type=int, default=3)
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

    def python(value: MazeGraph, origin: TileIndex) -> tuple[int, ...]:
        return bfs(value, origin).unwrap().distances

    implementations = (
        ("Python BFS", python),
        ("C++ graph one-shot", native_search(backend, "graph-one-shot")),
        ("C++ masked one-shot", native_search(backend, "masked-one-shot")),
        ("C++ graph cached", native_search(backend, "graph-cached")),
        ("C++ masked cached", native_search(backend, "masked-cached")),
        ("C++ selected cached", native_search(backend, "selected")),
    )

    reference_fields: list[tuple[int, ...]] = []
    for origin_value in range(len(graph.moves)):
        origin = TileIndex(origin_value)
        expected = python(graph, origin)
        reference_fields.append(expected)
        if any(search(graph, origin) != expected for _, search in implementations[1:]):
            print(f"distance mismatch at origin {origin_value}")
            backend.close()
            return 1

    print(f"maze: {args.width}x{args.height}, origins: {len(graph.moves)}")
    for name, search in implementations:
        search(graph, TileIndex(0))
        elapsed = measure(graph, search, args.rounds) / 1_000
        print(f"{name:22} {elapsed:9.2f} us/search")
    batch_elapsed = measure_batch(graph, backend, args.rounds) / 1_000
    print(f"{'C++ selected batch':22} {batch_elapsed:9.2f} us/field")
    abi_ns, decode_ns = measure_cached_abi(graph, backend, args.rounds)
    abi_elapsed = abi_ns / 1_000
    print(f"{'C++ ABI cached lookup':22} {abi_elapsed:9.2f} us/field")
    print(f"{'C++ Python result decode':22} {decode_ns / 1_000:9.2f} us/field")
    encoding_elapsed = measure_graph_encoding(graph, backend, args.rounds) / 1_000
    print(f"{'C++ Python graph encode':22} {encoding_elapsed:9.2f} us/graph")
    fixture = {
        "graph": encoded_graph(graph),
        "tileCount": len(graph.moves),
        "width": graph.width,
        "digest": sha256(json.dumps(reference_fields, separators=(",", ":")).encode()).hexdigest(),
    }
    with tempfile.TemporaryDirectory(prefix="pacman-bfs-") as directory:
        path = Path(directory) / "fixture.json"
        path.write_text(json.dumps(fixture), encoding="utf-8")
        completed = subprocess.run(
            ["node", "web/benchmark-pathfinding.mjs", str(path), str(args.rounds)],
            check=False,
        )
    backend.close()
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
