"""Compare Python and native BFS implementations on a generated maze."""

from argparse import ArgumentParser
from collections.abc import Callable
from hashlib import sha256
from statistics import median
from time import perf_counter_ns

from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.models import MazeGraph
from pacman.analyze.native_pathfinding import NativePathfinding, load_native_pathfinding
from pacman.analyze.pathfinding import bfs
from pacman.maze_loader import load_maze
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import Maze, MazeId, TileIndex
from typed_errs import Err, Nothing, Some

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


def native_search(backend: NativePathfinding, masked: bool | None) -> Search:
    """Create a callable for cached, graph, or one-shot masked native BFS.

    Returns:
        A uniform search callable for the selected native mode.
    """

    def search(graph: MazeGraph, origin: TileIndex) -> tuple[int, ...]:
        result = (
            backend.distances(graph, origin)
            if masked is None
            else backend.one_shot_distances(graph, origin, masked=masked)
        )
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
        ("C++ graph one-shot", native_search(backend, False)),
        ("C++ masked one-shot", native_search(backend, True)),
        ("C++ masked cached", native_search(backend, None)),
    )

    for origin_value in range(len(graph.moves)):
        origin = TileIndex(origin_value)
        expected = python(graph, origin)
        if any(search(graph, origin) != expected for _, search in implementations[1:]):
            print(f"distance mismatch at origin {origin_value}")
            backend.close()
            return 1

    print(f"maze: {args.width}x{args.height}, origins: {len(graph.moves)}")
    for name, search in implementations:
        search(graph, TileIndex(0))
        elapsed = measure(graph, search, args.rounds) / 1_000
        print(f"{name:22} {elapsed:9.2f} us/search")
    backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
