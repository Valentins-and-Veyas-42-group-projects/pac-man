# uv run python delete_me/replay/main.py
# Made by Codex as a disposable replay integration runner.

"""Exercise replay persistence through selectable integration cases."""

import argparse
from pathlib import Path

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
    Score,
    Tick,
    TileIndex,
)
from pacman.replay.store import ReplayStore

DB_PATH = Path("/tmp/pacman-replay-test.sqlite3")


def run(case: str) -> None:
    """Exercise the selected portion of the ReplayStore API.

    Args:
        case: Integration case to stop after, or ``all`` for the full flow.
    """
    DB_PATH.unlink(missing_ok=True)

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

    if case == "maze":
        return

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

    if case == "metadata":
        return

    print("\n== append frame batch ==")

    frame = Frame(
        tick=Tick(0),
        player=PlayerFrame(
            position=Position(
                x=Coord(0),
                y=Coord(0),
            ),
            direction=Direction.RIGHT,
        ),
        ghosts=(
            GhostFrame(
                ghost=Ghost.BLINKY,
                position=Position(
                    x=Coord(1),
                    y=Coord(1),
                ),
                direction=Direction.LEFT,
                state=GhostState.CHASE,
            ),
            GhostFrame(
                ghost=Ghost.PINKY,
                position=Position(
                    x=Coord(1),
                    y=Coord(0),
                ),
                direction=Direction.DOWN,
                state=GhostState.SCATTER,
            ),
            GhostFrame(
                ghost=Ghost.INKY,
                position=Position(
                    x=Coord(0),
                    y=Coord(1),
                ),
                direction=Direction.UP,
                state=GhostState.FRIGHTENED,
            ),
            GhostFrame(
                ghost=Ghost.CLYDE,
                position=Position(
                    x=Coord(1),
                    y=Coord(1),
                ),
                direction=Direction.RIGHT,
                state=GhostState.EATEN,
            ),
        ),
        score=Score(10),
        lives=3,
        phase=GamePhase.PLAYING,
    )

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

    if case == "frames":
        return

    print("\n== finish replay ==")

    store.finish(replay_id).unwrap()

    finished = store.replay(replay_id).unwrap()

    assert finished.ended_at is not None

    print("finish OK")

    print("\n== all tests passed ==")
    print(f"database: {DB_PATH}")


def main() -> None:
    """Select and run a replay integration case."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=("all", "maze", "metadata", "frames"),
        default="all",
    )
    args = parser.parse_args()
    run(args.case)


if __name__ == "__main__":
    main()
