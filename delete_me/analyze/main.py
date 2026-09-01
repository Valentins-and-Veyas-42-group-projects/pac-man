# uv run python -m delete_me.analyze.main --case graph --width 9 --height 7
# Made by Codex as a disposable graph inspection runner.

"""Generate a maze, build its analysis graph, and render the adjacency."""

import asyncio
import sys
from dataclasses import dataclass
from typing import cast

from cli_fw import Command, arg
from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.models import MazeGraph
from pacman.analyze.pathfinding import bfs, shortest_path
from pacman.analyze.state import analyze_frame
from pacman.maze_loader import load_maze
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import (
    Direction,
    Frame,
    GamePhase,
    Ghost,
    GhostFrame,
    GhostState,
    Maze,
    MazeId,
    PlayerFrame,
    Score,
    Tick,
    TileIndex,
)
from typed_errs import Err, Nothing, Option, Some

from delete_me.analyze.live_main import run as run_live

CASES = ["graph", "live"]


@dataclass
class AnalyzeArgs:
    """Arguments for the disposable graph preview."""

    case: str = cast(
        str,
        arg(help="Analysis demonstration to run", default="graph", choices=CASES),
    )
    width: int = cast(int, arg(help="Maze width", default=9))
    height: int = cast(int, arg(help="Maze height", default=7))
    seed: int = cast(int, arg(help="Random seed; use 0 for random", default=42))
    origin: int = cast(int, arg(help="Path origin tile", default=0))
    destination: int = cast(
        int,
        arg(help="Path destination tile; -1 selects the final tile", default=-1),
    )


def has_move(graph: MazeGraph, tile: TileIndex, direction: Direction) -> bool:
    """Return whether a graph tile has a move in one direction.

    Returns:
        Whether the directed edge exists.
    """
    return any(move.direction is direction for move in graph.neighbors(tile))


def render_graph(
    graph: MazeGraph,
    path: frozenset[TileIndex],
    origin: TileIndex,
    destination: TileIndex,
) -> str:
    """Render graph nodes and edges as compact ASCII.

    Returns:
        A multiline representation of the graph adjacency.
    """
    lines: list[str] = []

    for y in range(graph.height):
        node_line: list[str] = []
        down_line: list[str] = []

        for x in range(graph.width):
            tile = TileIndex(y * graph.width + x)
            label = f"{int(tile):03}"
            if tile == origin:
                node_line.append(f"S{label}S")
            elif tile == destination:
                node_line.append(f"D{label}D")
            elif tile in path:
                node_line.append(f"*{label}*")
            else:
                node_line.append(f" {label} ")
            if x < graph.width - 1:
                connector = "──" if has_move(graph, tile, Direction.RIGHT) else "  "
                node_line.append(connector)

            down = has_move(graph, tile, Direction.DOWN)
            down_line.append("  │  " if down else "     ")
            if x < graph.width - 1:
                down_line.append("  ")

        lines.append("".join(node_line))
        if y < graph.height - 1:
            lines.append("".join(down_line))

    return "\n".join(lines)


def run_graph(args: AnalyzeArgs) -> int:
    """Generate, encode, graph, and render one real maze.

    Returns:
        Zero after successful graph construction, otherwise one.
    """
    seed: Option[int] = Nothing() if args.seed == 0 else Some(args.seed)
    generated = load_maze(args.width, args.height, seed)
    if isinstance(generated, Err):
        generated.print_diagnostic()
        return 1

    topology = encode_topology(generated.value.cells)
    if isinstance(topology, Err):
        topology.print_diagnostic()
        return 1

    maze = Maze(
        id=MazeId(0),
        width=generated.value.width,
        height=generated.value.height,
        topology=topology.value,
        initial_collectibles=b"",
        checksum=b"graph-demo",
    )
    graph = build_maze_graph(maze)
    if isinstance(graph, Err):
        graph.print_diagnostic()
        return 1

    destination = (
        TileIndex(len(graph.value.moves) - 1)
        if args.destination == -1
        else TileIndex(args.destination)
    )
    origin = TileIndex(args.origin)
    field = bfs(graph.value, origin)
    if isinstance(field, Err):
        field.print_diagnostic()
        return 1
    path = shortest_path(field.value, destination)
    if isinstance(path, Nothing):
        print(f"no path from tile {origin} to tile {destination}")
        return 1

    for raw_tile, moves in enumerate(graph.value.moves):
        tile = TileIndex(raw_tile)
        position = maze.position(tile)
        expected = set(generated.value.neighbors(int(position.x), int(position.y)))
        actual = {
            (
                int(maze.position(move.destination).x),
                int(maze.position(move.destination).y),
            )
            for move in moves
        }
        if actual != expected:
            print(f"graph mismatch at tile {raw_tile}: {actual} != {expected}")
            return 1

    edge_count = sum(len(moves) for moves in graph.value.moves)
    middle_tile = path.value.tiles[len(path.value.tiles) // 2]
    player_direction = graph.value.neighbors(origin)[0].direction
    sample_frame = Frame(
        Tick(0),
        PlayerFrame(maze.position(origin), player_direction),
        (
            GhostFrame(
                Ghost.BLINKY,
                maze.position(destination),
                Direction.LEFT,
                GhostState.CHASE,
            ),
            GhostFrame(
                Ghost.INKY,
                maze.position(middle_tile),
                Direction.LEFT,
                GhostState.FRIGHTENED,
            ),
        ),
        Score(0),
        3,
        GamePhase.PLAYING,
    )
    state = analyze_frame(graph.value, maze, sample_frame)
    if isinstance(state, Err):
        state.print_diagnostic()
        return 1

    print(render_graph(graph.value, frozenset(path.value.tiles), origin, destination))
    print()
    print(f"size:           {graph.value.width}x{graph.value.height}")
    print(f"nodes:          {len(graph.value.moves)}")
    print(f"directed edges: {edge_count}")
    print(f"connections:    {edge_count // 2}")
    print(f"path:           {origin} -> {destination}")
    print(f"distance:       {path.value.distance}")
    print(f"tiles:          {tuple(int(tile) for tile in path.value.tiles)}")
    print()
    print("frame analysis:")
    print(f"  player tile:  {state.value.player_tile}")
    print(f"  topology:     {state.value.tile_kind.value}")
    print("  legal moves:  " + ", ".join(direction.name for direction in state.value.legal_actions))
    for ghost in state.value.ghost_distances:
        danger = "dangerous" if ghost.dangerous else "non-lethal"
        print(f"  {ghost.ghost.name:<7} tile={ghost.tile} distance={ghost.distance} {danger}")
    print("verified:       graph edges match maze movement")
    print("legend:         S=start, D=destination, *=shortest path")
    return 0


def run(args: AnalyzeArgs) -> int:
    """Run the selected headless-analysis demonstration.

    Returns:
        The selected demonstration's process status.
    """
    if args.case == "live":
        return asyncio.run(run_live())
    return run_graph(args)


def main() -> None:
    """Run the disposable maze-graph preview.

    Raises:
        SystemExit: With the graph preview status.
    """
    command = Command(
        name="analyze-dev",
        short="Exercise graph building or the live-analysis pipeline",
        schema=AnalyzeArgs,
        run=run,
    )
    result = command.execute(sys.argv[1:])
    if isinstance(result, Err):
        result.print_diagnostic()
        raise SystemExit(2)
    raise SystemExit(cast(int, result.value))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, Exception) as error:
        print(f"analyze-dev failed unexpectedly: {error}")
        raise SystemExit(1) from None
