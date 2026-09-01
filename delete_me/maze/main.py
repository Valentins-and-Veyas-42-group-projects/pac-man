# uv run python delete_me/maze/main.py --width 30 --height 20 --seed 42
# Made by Codex as a disposable maze integration runner.

"""Temporary CLI for generating and inspecting the assigned maze."""

import sys
from dataclasses import dataclass
from typing import cast

from cli_fw import Command, arg
from pacman.maze_loader import MazeError, Solver, load_maze
from typed_errs import Err, Nothing, Ok, Option, Result, Some


@dataclass
class MazeArgs:
    """Arguments for the temporary maze preview."""

    width: int = cast(int, arg(help="Maze width", default=30))
    height: int = cast(int, arg(help="Maze height", default=20))
    seed: int = cast(int, arg(help="Random seed; use 0 for a random maze", default=42))


def run(args: MazeArgs) -> Result[None, MazeError]:
    """Generate and inspect one maze through the Pac-Man adapter.

    Args:
        args: Parsed maze dimensions and seed.

    Returns:
        Ok after rendering the maze, or its typed generation error.
    """
    seed: Option[int] = Nothing() if args.seed == 0 else Some(args.seed)
    result = load_maze(width=args.width, height=args.height, seed=seed)

    match result:
        case Err() as error:
            return error
        case Ok(maze):
            rows = ["".join(format(cell, "X") for cell in row) for row in maze.cells]
            print("\n".join(rows))
            print()
            print(f"size:       {maze.width}x{maze.height}")
            print(f"entry:      {maze.entry}")
            print(f"exit:       {maze.exit}")
            print()

            print("entry checks:")
            print(f"  in bounds: {maze.in_bounds(*maze.entry)}")
            entry_neighbors = maze.neighbors(*maze.entry)
            print(f"  neighbors: {entry_neighbors}")
            print(f"  exits:     {len(entry_neighbors)}")
            print()

            print("exit checks:")
            print(f"  in bounds: {maze.in_bounds(*maze.exit)}")
            exit_neighbors = maze.neighbors(*maze.exit)
            print(f"  neighbors: {exit_neighbors}")
            print(f"  exits:     {len(exit_neighbors)}")
            print()

            print("movement from entry:")
            for name, dx, dy in (
                ("north", 0, -1),
                ("east", 1, 0),
                ("south", 0, 1),
                ("west", -1, 0),
            ):
                movable = maze.can_move(maze.entry[0], maze.entry[1], dx, dy)
                print(f"  {name:<5}: {movable}")
            print()

            bfs = maze.path(maze.entry, maze.exit, Solver.BFS)
            dfs = maze.path(maze.entry, maze.exit, Solver.DFS)
            print("pathfinding:")

            match bfs:
                case Some(path):
                    print(f"  BFS path length: {len(path)}")
                    print(f"  BFS first steps: {path[:10]}")
                case Nothing():
                    print("  BFS: no path")

            match dfs:
                case Some(path):
                    print(f"  DFS path length: {len(path)}")
                    print(f"  DFS first steps: {path[:10]}")
                case Nothing():
                    print("  DFS: no path")

            return Ok(None)


def main() -> None:
    """Run the temporary maze development command.

    Raises:
        SystemExit: When maze generation fails.
    """
    command = Command(
        name="maze-dev",
        short="Generate and inspect the Pac-Man maze",
        schema=MazeArgs,
        run=run,
    )
    result = command.execute(sys.argv[1:])
    if isinstance(result, Err):
        result.print_diagnostic()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
