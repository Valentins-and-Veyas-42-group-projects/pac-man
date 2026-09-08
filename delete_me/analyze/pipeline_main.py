"""Run a two-minute fake game through storage and process analysis."""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from random import Random
from time import perf_counter

from pacman.analyze.maze_graph import build_maze_graph
from pacman.analyze.messages import (
    AnalysisMessage,
    DeathQueued,
    DecisionEvaluationQueued,
    TurnObserved,
)
from pacman.analyze.models import MazeGraph, Move
from pacman.analyze.pathfinding import bfs
from pacman.analyze.simulation import SimulationRules
from pacman.maze_loader import load_maze
from pacman.replay.maze_codec import encode_collectibles, encode_topology
from pacman.replay.models import (
    Collectible,
    CollectibleChange,
    Direction,
    EncodedMaze,
    Frame,
    GamePhase,
    Ghost,
    GhostFrame,
    GhostState,
    Maze,
    PlayerFrame,
    ReplayId,
    Score,
    Tick,
    TileIndex,
)
from pacman.replay.pipeline import ReplayPipeline
from pacman.replay.store import ReplayStore
from typed_concurrency import Group
from typed_errs import Err, Nothing, Option, Some

from delete_me.analyze.experiment_store import ExperimentResult, ExperimentStore

DB_PATH = Path("/tmp/pacman-analysis-pipeline.sqlite3")
HISTORY_PATH = Path("/tmp/pacman-analysis-history.sqlite3")
TICK_HZ = 60
RENDER_HZ = 10
MOVE_EVERY_TICKS = 6


@dataclass(frozen=True, slots=True)
class FakeGameStep:
    """One generated frame and its external replay effects."""

    frame: Frame
    collectible_change: Option[CollectibleChange]
    notices: tuple[str, ...]


@dataclass(slots=True)
class FakeGame:
    """Small seeded graph simulation used only by the pipeline demo."""

    replay_id: ReplayId
    maze: Maze
    graph: MazeGraph
    rng: Random
    fumble_rate: float
    player_tile: TileIndex
    ghost_tiles: dict[Ghost, TileIndex]
    collectibles: list[Collectible]
    initial_collectibles: tuple[Collectible, ...]
    player_direction: Direction = Direction.RIGHT
    ghost_directions: dict[Ghost, Direction] = field(default_factory=dict)
    eaten_until: dict[Ghost, int] = field(default_factory=dict)
    frightened_until: int = 0
    score: int = 0
    lives: int = 3
    fumbles: int = 0
    pickups: int = 0
    deaths: int = 0
    wins: int = 0
    losses: int = 0
    bad_play_ticks: list[int] = field(default_factory=list)
    reset_pending: bool = False

    def step(self, tick: int) -> FakeGameStep:
        """Advance the random game by one replay tick.

        Returns:
            Frame, collectible mutation, and notable simulation events.
        """
        notices: list[str] = []
        change: Option[CollectibleChange] = Nothing()
        phase = GamePhase.PLAYING
        if self.reset_pending:
            self._reset_positions()
            self.reset_pending = False

        if tick % MOVE_EVERY_TICKS == 0:
            self._move_ghosts(tick)
            fumbled = self._move_player()
            if fumbled:
                self.fumbles += 1
                self.bad_play_ticks.append(tick)
                notices.append(f"tick {tick:>4}: FUMBLE chose the lowest-scoring legal move")
            change, pickup = self._collect(tick)
            if isinstance(pickup, Some):
                notices.append(pickup.value)
            if self._lethal_collision(tick):
                phase = GamePhase.DYING
                self.deaths += 1
                self.lives -= 1
                notices.append(f"tick {tick:>4}: lethal ghost collision, life lost")
                if self.lives == 0:
                    self.losses += 1
                    self.lives = 3
                    self._reset_collectibles()
                    notices.append(f"tick {tick:>4}: LOSS, new fake game started")
                self.reset_pending = True
            elif not any(collectible is not Collectible.NONE for collectible in self.collectibles):
                self.wins += 1
                self.lives = 3
                self._reset_collectibles()
                self.reset_pending = True
                notices.append(f"tick {tick:>4}: WIN, every collectible cleared")

        ghosts = tuple(
            GhostFrame(
                ghost,
                self.maze.position(self.ghost_tiles[ghost]),
                self.ghost_directions.get(ghost, Direction.LEFT),
                self._ghost_state(ghost, tick),
            )
            for ghost in Ghost
        )
        return FakeGameStep(
            Frame(
                Tick(tick),
                PlayerFrame(self.maze.position(self.player_tile), self.player_direction),
                ghosts,
                Score(self.score),
                self.lives,
                phase,
            ),
            change,
            tuple(notices),
        )

    def _move_player(self) -> bool:
        moves = self.graph.neighbors(self.player_tile)
        scored = tuple((self._score_move(move), self.rng.random(), move) for move in moves)
        fumbled = len(scored) > 1 and self.rng.random() < self.fumble_rate
        selector = min if fumbled else max
        selected = selector(scored, key=lambda item: (item[0], item[1]))
        self.player_tile = selected[2].destination
        self.player_direction = selected[2].direction
        return fumbled

    def _score_move(self, move: Move) -> int:
        field = bfs(self.graph, move.destination).unwrap()
        nearest_ghost = min(field.distances[int(tile)] for tile in self.ghost_tiles.values())
        collectible = self.collectibles[int(move.destination)]
        collectible_value = 80 if collectible is Collectible.POWER_PELLET else 20
        if collectible is Collectible.NONE:
            collectible_value = 0
        reverse_penalty = -4 if move.direction is opposite(self.player_direction) else 0
        return collectible_value + min(nearest_ghost, 12) * 3 + reverse_penalty

    def _move_ghosts(self, tick: int) -> None:
        for ghost in Ghost:
            if tick < self.eaten_until.get(ghost, 0):
                continue
            moves = self.graph.neighbors(self.ghost_tiles[ghost])
            previous = self.ghost_directions.get(ghost, Direction.LEFT)
            forward = tuple(move for move in moves if move.direction is not opposite(previous))
            choices = forward if forward else moves
            move = self.rng.choice(choices)
            self.ghost_tiles[ghost] = move.destination
            self.ghost_directions[ghost] = move.direction

    def _collect(self, tick: int) -> tuple[Option[CollectibleChange], Option[str]]:
        collectible = self.collectibles[int(self.player_tile)]
        if collectible is Collectible.NONE:
            return Nothing(), Nothing()
        self.collectibles[int(self.player_tile)] = Collectible.NONE
        self.pickups += 1
        points = 50 if collectible is Collectible.POWER_PELLET else 10
        self.score += points
        if collectible is Collectible.POWER_PELLET:
            self.frightened_until = tick + 8 * TICK_HZ
        return (
            Some(CollectibleChange(Tick(tick), self.player_tile, Collectible.NONE)),
            Some(f"tick {tick:>4}: picked up {collectible.name.lower()} (+{points})"),
        )

    def _lethal_collision(self, tick: int) -> bool:
        for ghost, tile in self.ghost_tiles.items():
            if tile != self.player_tile:
                continue
            if self._ghost_state(ghost, tick) is GhostState.FRIGHTENED:
                self.eaten_until[ghost] = tick + 2 * TICK_HZ
                self.score += 200
                return False
            if self._ghost_state(ghost, tick) is GhostState.CHASE:
                return True
        return False

    def _ghost_state(self, ghost: Ghost, tick: int) -> GhostState:
        if tick < self.eaten_until.get(ghost, 0):
            return GhostState.EATEN
        if tick < self.frightened_until:
            return GhostState.FRIGHTENED
        return GhostState.CHASE

    def _reset_positions(self) -> None:
        self.player_tile = TileIndex(0)
        last = len(self.graph.moves) - 1
        self.ghost_tiles = {ghost: TileIndex(max(0, last - int(ghost) * 3)) for ghost in Ghost}

    def _reset_collectibles(self) -> None:
        self.collectibles[:] = self.initial_collectibles


def opposite(direction: Direction) -> Direction:
    """Return the opposite cardinal direction."""
    return Direction((int(direction) + 2) % 4)


def has_direction(graph: MazeGraph, tile: TileIndex, direction: Direction) -> bool:
    """Return whether a graph tile has an edge in one direction."""
    return any(move.direction is direction for move in graph.neighbors(tile))


def render_maze(
    graph: MazeGraph,
    frame: Frame,
    collectibles: list[Collectible],
) -> str:
    """Render maze connections and current actors.

    Returns:
        Compact terminal representation of the current frame.
    """
    actors: dict[TileIndex, str] = {
        TileIndex(int(ghost.position.y) * graph.width + int(ghost.position.x)): ghost.ghost.name[0]
        for ghost in frame.ghosts
    }
    player_tile = TileIndex(int(frame.player.position.y) * graph.width + int(frame.player.position.x))
    actors[player_tile] = "X" if player_tile in actors else "P"
    lines: list[str] = []
    for y in range(graph.height):
        nodes: list[str] = []
        verticals: list[str] = []
        for x in range(graph.width):
            tile = TileIndex(y * graph.width + x)
            collectible = collectibles[int(tile)]
            floor = "o" if collectible is Collectible.POWER_PELLET else "·"
            if collectible is Collectible.NONE:
                floor = " "
            nodes.append(actors.get(tile, floor))
            if x < graph.width - 1:
                nodes.append("─" if has_direction(graph, tile, Direction.RIGHT) else " ")
            verticals.append("│" if has_direction(graph, tile, Direction.DOWN) else " ")
            if x < graph.width - 1:
                verticals.append(" ")
        lines.append("".join(nodes))
        if y < graph.height - 1:
            lines.append("".join(verticals))
    return "\n".join(lines)


def describe_message(message: AnalysisMessage) -> str:
    """Turn one typed analyzer message into a concise event line.

    Returns:
        Human-readable event description.
    """
    if isinstance(message, TurnObserved):
        return f"tick {int(message.tick):>4}: player turned"
    if isinstance(message, DecisionEvaluationQueued):
        return f"tick {int(message.evaluation_tick):>4}: evaluated turn from tick {int(message.decision_tick)}"
    return f"tick {int(message.tick):>4}: death analysis queued"


def render_live(
    graph: MazeGraph,
    frame: Frame,
    recent_events: deque[str],
    elapsed: float,
    analysis_events: int,
    rejected_batches: int,
    game: FakeGame,
    game_ticks: int,
    speed: float,
) -> None:
    """Replace the terminal view with current simulation and runtime metrics."""
    simulated = int(frame.tick) / TICK_HZ
    progress = (int(frame.tick) + 1) / game_ticks
    total_seconds = game_ticks / TICK_HZ
    bar_width = 30
    filled = int(progress * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    throughput = (int(frame.tick) + 1) / max(elapsed, 0.001)
    lines = [
        "\033[2J\033[H== live random replay pipeline ==",
        f"[{bar}] {simulated:6.1f}/{total_seconds:.1f} s  tick {int(frame.tick):,}  speed {speed:g}x",
        f"runtime {elapsed:6.2f} s  throughput {throughput:7.1f} frames/s",
        f"analysis events {analysis_events:,}  rejected batches {rejected_batches}",
        f"score {game.score:,}  lives {game.lives}  pickups {game.pickups}",
        f"fumbles {game.fumbles}  deaths {game.deaths}",
        "legend: P=Pac-Man B/P/I/C=ghost X=collision ·=pacgum o=power pellet",
        "",
        render_maze(graph, frame, game.collectibles),
        "",
        "recent analyzer events:",
        *(recent_events if recent_events else ("waiting for first recorder batch...",)),
    ]
    print("\n".join(lines), end="", flush=True)


async def run(
    width: int,
    height: int,
    seed: int,
    seconds: int,
    speed: float,
    fumble_rate: float,
) -> int:
    """Simulate, persist, analyze, and report one configurable game.

    Returns:
        Zero after both consumers drain, otherwise one.
    """
    if seconds <= 0 or speed <= 0 or not 0.0 <= fumble_rate <= 1.0:
        print("seconds and speed must be positive; fumble-rate must be between 0 and 1")
        return 2
    game_ticks = seconds * TICK_HZ
    selected_seed: Option[int] = Nothing() if seed == 0 else Some(seed)
    generated = load_maze(width, height, selected_seed)
    if isinstance(generated, Err):
        generated.print_diagnostic()
        return 1
    topology = encode_topology(generated.value.cells)
    setup_rng = Random(seed if seed != 0 else None)
    collectible_state = [
        Collectible.POWER_PELLET if setup_rng.random() < 0.06 else Collectible.PACGUM
        for _ in range(generated.value.width * generated.value.height)
    ]
    entry_tile = generated.value.entry[1] * generated.value.width + generated.value.entry[0]
    collectible_state[entry_tile] = Collectible.NONE
    encoded_collectibles = encode_collectibles(collectible_state)
    if isinstance(topology, Err) or isinstance(encoded_collectibles, Err):
        print("failed to encode generated maze")
        return 1

    DB_PATH.unlink(missing_ok=True)
    store = ReplayStore(DB_PATH)
    store.initialize_replay().unwrap()
    checksum = sha256(topology.value + encoded_collectibles.value).digest()
    maze_id = store.create_maze(
        EncodedMaze(
            generated.value.width,
            generated.value.height,
            generated.value.entry,
            generated.value.exit,
            topology.value,
            encoded_collectibles.value,
            checksum,
        )
    ).unwrap()
    replay_id = store.create_replay(maze_id, TICK_HZ, 1, 1, b"pipeline-demo", seed).unwrap()
    maze = Maze(
        maze_id,
        generated.value.width,
        generated.value.height,
        topology.value,
        encoded_collectibles.value,
        checksum,
    )
    graph = build_maze_graph(maze)
    if isinstance(graph, Err):
        graph.print_diagnostic()
        return 1
    pipeline = ReplayPipeline.create(
        replay_id,
        store,
        maze,
        SimulationRules(),
        buffer_size=240,
        analysis_capacity=32,
    ).unwrap()

    last_tile = len(graph.value.moves) - 1
    game = FakeGame(
        replay_id,
        maze,
        graph.value,
        Random(seed if seed != 0 else None),
        fumble_rate,
        TileIndex(entry_tile),
        {ghost: TileIndex(max(0, last_tile - int(ghost) * 3)) for ghost in Ghost},
        collectible_state,
        tuple(collectible_state),
    )

    started_at = perf_counter()
    recent_events: deque[str] = deque(maxlen=6)
    analysis_events = 0
    last_frame: Option[Frame] = Nothing()
    render_interval = max(1, int(TICK_HZ * speed / RENDER_HZ))
    async with Group() as group:
        group << pipeline.run_storage()
        pipeline.start().unwrap()
        for tick in range(game_ticks):
            step = game.step(tick)
            frame = step.frame
            last_frame = Some(frame)
            if isinstance(step.collectible_change, Some):
                pipeline.on_collectible_change(step.collectible_change.value)
            recent_events.extend(step.notices)
            await pipeline.on_frame(frame)
            if tick % render_interval == 0:
                messages = pipeline.drain_analysis()
                analysis_events += len(messages)
                recent_events.extend(describe_message(message) for message in messages)
                elapsed = perf_counter() - started_at
                render_live(
                    graph.value,
                    frame,
                    recent_events,
                    elapsed,
                    analysis_events,
                    pipeline.rejected_offer_count,
                    game,
                    game_ticks,
                    speed,
                )
            target = started_at + (tick + 1) / (TICK_HZ * speed)
            delay = target - perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
        report = (await pipeline.finish()).unwrap()

    trailing_messages = report.messages[analysis_events:]
    recent_events.extend(describe_message(message) for message in trailing_messages)
    if isinstance(last_frame, Nothing):
        print("simulation produced no frames")
        return 1
    render_live(
        graph.value,
        last_frame.value,
        recent_events,
        perf_counter() - started_at,
        len(report.messages),
        len(report.rejected_offers),
        game,
        game_ticks,
        speed,
    )
    turns = sum(isinstance(message, TurnObserved) for message in report.messages)
    evaluations = sum(isinstance(message, DecisionEvaluationQueued) for message in report.messages)
    deaths = sum(isinstance(message, DeathQueued) for message in report.messages)
    print("\n\n== final pipeline summary ==")
    print(f"simulated:        {seconds} seconds at {TICK_HZ} Hz and {speed:g}x")
    print(f"frames stored:    {report.frames:,}")
    print(f"batches analyzed: {report.analyzed_batches}/{report.batches}")
    print(f"analysis output:  {turns} turns, {evaluations} evaluations, {deaths} death")
    print(f"backpressure:     {len(report.rejected_offers)} rejected batches")
    print(f"game events:      {game.pickups} pickups, {game.fumbles} fumbles, {game.deaths} deaths")
    print(f"final score:      {game.score:,}")
    history = ExperimentStore(HISTORY_PATH)
    initialized = history.initialize_experiments()
    if isinstance(initialized, Err):
        initialized.print_diagnostic()
        return 1
    saved = history.save(
        ExperimentResult(
            seed=seed,
            seconds=seconds,
            speed=speed,
            fumble_probability=fumble_rate,
            frames=report.frames,
            score=game.score,
            pickups=game.pickups,
            fumbles=game.fumbles,
            deaths=game.deaths,
            wins=game.wins,
            losses=game.losses,
            bad_play_ticks=tuple(game.bad_play_ticks),
        )
    )
    if isinstance(saved, Err):
        saved.print_diagnostic()
        return 1
    completed = game.wins + game.losses
    win_rate = "n/a" if completed == 0 else f"{game.wins / completed:.1%}"
    print(f"round results:    {game.wins} wins, {game.losses} losses, {win_rate} win rate")
    print(f"bad-play ticks:   {tuple(game.bad_play_ticks)}")
    print(f"experiment:       #{int(saved.value)} in {HISTORY_PATH}")
    print(f"database:         {DB_PATH}")
    print("verified:         writer drained and analysis process stopped")
    return 0


def show_history() -> int:
    """Print saved experiments, bad plays, and aggregate win rate.

    Returns:
        Zero after history loads, otherwise one.
    """
    history = ExperimentStore(HISTORY_PATH)
    initialized = history.initialize_experiments()
    if isinstance(initialized, Err):
        initialized.print_diagnostic()
        return 1
    recent = history.recent(20)
    if isinstance(recent, Err):
        recent.print_diagnostic()
        return 1
    wins = sum(item.result.wins for item in recent.value)
    losses = sum(item.result.losses for item in recent.value)
    completed = wins + losses
    win_rate = "n/a" if completed == 0 else f"{wins / completed:.1%}"
    print("== saved random-game experiments ==")
    print(f"runs: {len(recent.value)}  rounds: {completed}  wins: {wins}  losses: {losses}  win rate: {win_rate}")
    for item in recent.value:
        result = item.result
        ticks = ", ".join(str(tick) for tick in result.bad_play_ticks[:12])
        if len(result.bad_play_ticks) > 12:
            ticks += ", ..."
        print(
            f"#{int(item.id):<3} seed={result.seed:<5} p={result.fumble_probability:.2f} "
            f"score={result.score:<6} W/L={result.wins}/{result.losses} "
            f"bad plays=[{ticks}]"
        )
    print(f"database: {HISTORY_PATH}")
    return 0
