# uv run python delete_me/replay/main.py --case stress --frames 1000000
# Made by Codex as a disposable replay integration runner.

"""Exercise replay persistence through selectable integration cases."""

import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import cast

from cli_fw import Command, arg
from pacman.replay.models import (
    Collectible,
    CollectibleChange,
    Coord,
    Direction,
    EncodedMaze,
    Frame,
    FrameBatch,
    GamePhase,
    Ghost,
    GhostFrame,
    GhostState,
    PlayerFrame,
    Position,
    ReplayId,
    Score,
    Tick,
    TileIndex,
)
from pacman.replay.store import ReplayStore
from typed_errs import Err

DB_PATH = Path("/tmp/pacman-replay-test.sqlite3")
CASES = ["all", "maze", "metadata", "frames", "stress"]


@dataclass
class ReplayArgs:
    """Arguments accepted by the disposable replay runner."""

    case: str = cast(
        str,
        arg(default="all", choices=CASES, help="Replay exercise to run"),
    )
    frames: int = cast(
        int,
        arg(default=1_000_000, help="Frames written by the stress case"),
    )
    batch_size: int = cast(
        int,
        arg(default=10_000, help="Frames per SQLite transaction"),
    )
    keep_db: bool = cast(
        bool,
        arg(default=False, help="Keep the generated database for inspection"),
    )


def replay_frame(tick: int, four_ghosts: bool = True) -> Frame:
    """Build a deterministic frame for integration testing.

    Args:
        tick: Simulation tick stored in the frame.
        four_ghosts: Whether to include every ghost or only Blinky.

    Returns:
        A representative replay frame.
    """
    ghosts = (
        GhostFrame(
            ghost=Ghost.BLINKY,
            position=Position(x=Coord(1), y=Coord(1)),
            direction=Direction.LEFT,
            state=GhostState.CHASE,
        ),
        GhostFrame(
            ghost=Ghost.PINKY,
            position=Position(x=Coord(1), y=Coord(0)),
            direction=Direction.DOWN,
            state=GhostState.SCATTER,
        ),
        GhostFrame(
            ghost=Ghost.INKY,
            position=Position(x=Coord(0), y=Coord(1)),
            direction=Direction.UP,
            state=GhostState.FRIGHTENED,
        ),
        GhostFrame(
            ghost=Ghost.CLYDE,
            position=Position(x=Coord(1), y=Coord(1)),
            direction=Direction.RIGHT,
            state=GhostState.EATEN,
        ),
    )
    return Frame(
        tick=Tick(tick),
        player=PlayerFrame(
            position=Position(x=Coord(tick % 2), y=Coord((tick // 2) % 2)),
            direction=Direction(tick % 4),
        ),
        ghosts=ghosts if four_ghosts else ghosts[:1],
        score=Score(tick * 10),
        lives=3,
        phase=GamePhase.PLAYING,
    )


def database_size(path: Path) -> int:
    """Return the combined SQLite database, WAL, and shared-memory size."""
    paths = (path, Path(f"{path}-wal"), Path(f"{path}-shm"))
    return sum(candidate.stat().st_size for candidate in paths if candidate.exists())


def remove_database(path: Path) -> None:
    """Remove a SQLite database and its temporary sidecar files."""
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        candidate.unlink(missing_ok=True)


def stress(store: ReplayStore, replay_id: ReplayId, args: ReplayArgs) -> int:
    """Write and verify a large replay while reporting storage costs.

    Args:
        store: Initialized replay store.
        replay_id: Replay receiving generated frames.
        args: Stress-test controls.

    Returns:
        Zero after a successful write and verification.
    """
    if args.frames <= 0 or args.batch_size <= 0:
        print("frames and batch-size must both be greater than zero")
        return 2

    started = perf_counter()
    for offset in range(0, args.frames, args.batch_size):
        stop = min(offset + args.batch_size, args.frames)
        frames = tuple(replay_frame(tick, four_ghosts=False) for tick in range(offset, stop))
        store.append(FrameBatch(replay_id, frames, ())).unwrap()

    elapsed = perf_counter() - started
    for tick in (0, args.frames // 2, args.frames - 1):
        assert store.frame(replay_id, Tick(tick)).unwrap() == replay_frame(tick, four_ghosts=False)

    size = database_size(DB_PATH)
    print("\n== stress results ==")
    print(f"frames:       {args.frames:,}")
    print(f"elapsed:      {elapsed:.2f} s")
    print(f"throughput:   {args.frames / elapsed:,.0f} frames/s")
    print(f"database:     {size / 1_048_576:.2f} MiB")
    print(f"bytes/frame:  {size / args.frames:.1f}")
    print("verified:     first, middle, last")
    return 0


def run(args: ReplayArgs) -> int:
    """Exercise the selected portion of the ReplayStore API.

    Args:
        args: Selected integration case and stress-test controls.

    Returns:
        Zero when the selected replay exercise succeeds.
    """
    remove_database(DB_PATH)

    store = ReplayStore(DB_PATH)

    print("== initialize ==")

    store.initialize_replay().unwrap()

    print("OK")

    print("\n== create maze ==")

    maze = EncodedMaze(
        width=2,
        height=2,
        entry=(0, 0),
        exit=(1, 1),
        topology=b"\x12\x34",
        initial_collectibles=b"\x55",
        checksum=b"test-checksum",
    )

    maze_id = store.create_maze(maze).unwrap()

    print(f"created maze: {maze_id}")

    print("\n== load maze ==")

    loaded_maze = store.maze(maze_id).unwrap()

    assert loaded_maze == maze

    print("maze roundtrip OK")

    if args.case == "maze":
        return 0

    print("\n== create replay ==")

    replay_id = store.create_replay(
        maze_id=maze_id,
        tick_hz=60,
        level=1,
        simulation_version=1,
        config_hash=b"test-config",
        rng_seed=42,
    ).unwrap()

    print(f"created replay: {replay_id}")

    print("\n== load replay ==")

    replay = store.replay(replay_id).unwrap()

    assert replay.id == replay_id
    assert replay.maze_id == maze_id
    assert replay.ended_at is None
    assert replay.tick_hz == 60
    assert replay.level == 1
    assert replay.simulation_version == 1
    assert replay.config_hash == b"test-config"
    assert replay.rng_seed == 42

    print("replay roundtrip OK")

    if args.case == "metadata":
        return 0

    if args.case == "stress":
        result = stress(store, replay_id, args)
        if not args.keep_db:
            remove_database(DB_PATH)
        return result

    print("\n== append frame batch ==")

    frame = replay_frame(0)

    change = CollectibleChange(
        tick=Tick(0),
        tile=TileIndex(0),
        collectible=Collectible.PACGUM,
    )

    batch = FrameBatch(
        replay_id=replay_id,
        frames=(frame,),
        collectible_changes=(change,),
    )

    store.append(batch).unwrap()

    print("batch append OK")

    print("\n== load frame ==")

    loaded_frame = store.frame(
        replay_id,
        Tick(0),
    ).unwrap()

    assert loaded_frame == frame

    print("frame roundtrip OK")

    print("\n== snapshot ==")

    snapshot = store.snapshot(
        replay_id,
        Tick(0),
    ).unwrap()

    assert snapshot.replay_id == replay_id
    assert snapshot.tick == Tick(0)
    assert snapshot.player == frame.player
    assert snapshot.ghosts == frame.ghosts
    assert snapshot.score == frame.score
    assert snapshot.lives == frame.lives
    assert snapshot.phase == frame.phase

    print("snapshot reconstruction OK")

    if args.case == "frames":
        return 0

    print("\n== finish replay ==")

    store.finish(replay_id).unwrap()

    finished = store.replay(replay_id).unwrap()

    assert finished.ended_at is not None

    print("finish OK")

    print("\n== all tests passed ==")
    print(f"database: {DB_PATH}")
    return 0


def main() -> None:
    """Select and run a replay integration case.

    Raises:
        SystemExit: With the selected exercise status.
    """
    command = Command(
        name="replay-test",
        short="Exercise replay persistence and storage costs",
        long="Run quick replay checks or write a large replay in bounded batches",
        example=(
            "uv run python delete_me/replay/main.py --case stress "
            "--frames 1000000 --batch_size 10000"
        ),
        schema=ReplayArgs,
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
        print(f"replay-test failed unexpectedly: {error}")
        raise SystemExit(1) from None
