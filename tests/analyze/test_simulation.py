from pacman.analyze.collectibles import CollectibleField
from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.prediction import GhostPrediction, PredictedGhostState
from pacman.analyze.simulation import SimulationRules, simulate_action
from pacman.replay.maze_codec import encode_topology
from pacman.replay.models import (
    Collectible,
    Direction,
    Ghost,
    GhostState,
    Maze,
    MazeId,
    TileIndex,
)


def corridor(open_boundaries: bool = False) -> tuple[Maze, CollectibleField]:
    cells = [5, 5, 5] if open_boundaries else [13, 5, 7]
    maze = Maze(
        MazeId(1),
        3,
        1,
        encode_topology([cells]).unwrap(),
        b"",
        b"simulation-test",
    )
    return maze, CollectibleField((Collectible.NONE, Collectible.PACGUM, Collectible.POWER_PELLET))


def prediction(tile: int, tick: int, state: GhostState) -> GhostPrediction:
    ticks: list[tuple[PredictedGhostState, ...]] = [() for _ in range(tick + 1)]
    ticks[tick] = (
        PredictedGhostState(
            Ghost.BLINKY,
            TileIndex(tile),
            Direction.LEFT,
            tick,
            state,
        ),
    )
    return GhostPrediction(Ghost.BLINKY, tuple(ticks))


def test_simulation_collects_each_pacgum_only_once() -> None:
    maze, collectibles = corridor()
    simulation = simulate_action(
        build_maze_graph(maze).unwrap(),
        collectibles,
        (),
        TileIndex(0),
        Direction.RIGHT,
        SimulationRules(horizon_ticks=3),
    ).unwrap()

    assert {state.score_gained for state in simulation.terminals} == {10, 60}
    assert max(state.pacgums_eaten for state in simulation.terminals) == 1


def test_dangerous_contact_kills_branch() -> None:
    maze, collectibles = corridor()
    result = simulate_action(
        build_maze_graph(maze).unwrap(),
        collectibles,
        (prediction(1, 1, GhostState.CHASE),),
        TileIndex(0),
        Direction.RIGHT,
        SimulationRules(horizon_ticks=2),
    ).unwrap()

    assert result.terminals[0].died
    assert result.terminals[0].tick == 1


def test_power_pellet_turns_contact_into_ghost_score() -> None:
    maze, _ = corridor()
    collectibles = CollectibleField((Collectible.NONE, Collectible.POWER_PELLET, Collectible.NONE))
    result = simulate_action(
        build_maze_graph(maze).unwrap(),
        collectibles,
        (prediction(1, 1, GhostState.CHASE),),
        TileIndex(0),
        Direction.RIGHT,
        SimulationRules(horizon_ticks=1),
    ).unwrap()

    terminal = result.terminals[0]
    assert not terminal.died
    assert terminal.score_gained == 250
    assert terminal.eaten_ghosts == frozenset((Ghost.BLINKY,))


def test_simulation_uses_tunnel_as_first_action() -> None:
    maze, collectibles = corridor(open_boundaries=True)
    result = simulate_action(
        build_maze_graph(maze).unwrap(),
        collectibles,
        (),
        TileIndex(0),
        Direction.LEFT,
        SimulationRules(horizon_ticks=1),
    ).unwrap()

    assert result.terminals[0].path == (TileIndex(0), TileIndex(2))
    assert result.terminals[0].power_pellets_eaten == 1
