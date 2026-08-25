"""SQLite persistence for game replays."""

from importlib.resources import files
from time import time
from typing import cast

from sqlite_callback_store import (
    SQLiteStore,
    StorageError,
    Transaction,
)
from typed_errs import Err, Ok, Result

from .models import (
    Coord,
    Direction,
    EncodedMaze,
    Frame,
    FrameBatch,
    GamePhase,
    GameSnapshot,
    Ghost,
    GhostFrame,
    GhostState,
    Maze,
    MazeId,
    PlayerFrame,
    Position,
    ReplayId,
    ReplayMetadata,
    Score,
    Tick,
)


def _schema() -> str:
    """Load the bundled replay SQLite schema."""
    return (
        files("pacman.replay")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )


class ReplayStore(SQLiteStore):
    """Persist and reconstruct game replay data."""

    def initialize_replay(
        self,
    ) -> Result[None, StorageError]:
        """Initialize the replay database schema."""
        return self.initialize(_schema())

    def create_maze(
        self,
        maze: EncodedMaze,
    ) -> Result[MazeId, StorageError]:
        """Persist a maze and return its identifier."""

        def insert(
            transaction: Transaction,
        ) -> Result[MazeId, StorageError]:
            try:
                row = cast(
                    "tuple[int] | None",
                    transaction.connection.execute(
                        INSERT_MAZE,
                        (
                            maze.width,
                            maze.height,
                            maze.entry[0],
                            maze.entry[1],
                            maze.exit[0],
                            maze.exit[1],
                            maze.topology,
                            maze.initial_collectibles,
                            maze.checksum,
                        ),
                    ).fetchone(),
                )

                if row is None:
                    return Err(
                        error=StorageError.OPERATION_FAILED,
                        namespace="replay_store",
                        context_msg="Maze insert returned no identifier",
                    )

                return Ok(MazeId(row[0]))

            except Exception:
                return Err(
                    error=StorageError.QUERY_FAILED,
                    namespace="replay_store",
                    context_msg="Failed to insert maze",
                )

        return self.transaction(insert)

    def maze(
        self,
        maze_id: MazeId,
    ) -> Result[EncodedMaze, StorageError]:
        """Load a persisted maze."""

        def select(
            transaction: Transaction,
        ) -> Result[EncodedMaze, StorageError]:
            try:
                row = cast(
                    "tuple[int, int, int, int, int, int, bytes, bytes, bytes] | None",
                    transaction.connection.execute(
                        SELECT_MAZE,
                        (int(maze_id),),
                    ).fetchone(),
                )

                if row is None:
                    return Err(
                        error=StorageError.OPERATION_FAILED,
                        namespace="replay_store",
                        context_msg="Maze not found",
                    )

                return Ok(
                    EncodedMaze(
                        width=row[0],
                        height=row[1],
                        entry=(row[2], row[3]),
                        exit=(row[4], row[5]),
                        topology=row[6],
                        initial_collectibles=row[7],
                        checksum=row[8],
                    )
                )

            except Exception:
                return Err(
                    error=StorageError.QUERY_FAILED,
                    namespace="replay_store",
                    context_msg="Failed to load maze",
                )

        return self.transaction(select)

    def create_replay(
        self,
        maze_id: MazeId,
        tick_hz: int,
        level: int,
        simulation_version: int,
        config_hash: bytes,
        rng_seed: int,
    ) -> Result[ReplayId, StorageError]:
        """Create a replay and return its identifier."""

        def insert(
            transaction: Transaction,
        ) -> Result[ReplayId, StorageError]:
            try:
                row = cast(
                    "tuple[int] | None",
                    transaction.connection.execute(
                        INSERT_REPLAY,
                        (
                            int(maze_id),
                            int(time()),
                            tick_hz,
                            level,
                            simulation_version,
                            config_hash,
                            rng_seed,
                        ),
                    ).fetchone(),
                )

                if row is None:
                    return Err(
                        error=StorageError.OPERATION_FAILED,
                        namespace="replay_store",
                        context_msg="Replay insert returned no identifier",
                    )

                return Ok(ReplayId(row[0]))

            except Exception:
                return Err(
                    error=StorageError.QUERY_FAILED,
                    namespace="replay_store",
                    context_msg="Failed to create replay",
                )

        return self.transaction(insert)

    def replay(
        self,
        replay_id: ReplayId,
    ) -> Result[ReplayMetadata, StorageError]:
        """Load replay metadata."""

        def select(
            transaction: Transaction,
        ) -> Result[ReplayMetadata, StorageError]:
            try:
                row = cast(
                    "tuple[int, int, int, int | None, int, int, int, bytes, int] | None",
                    transaction.connection.execute(
                        SELECT_REPLAY,
                        (int(replay_id),),
                    ).fetchone(),
                )

                if row is None:
                    return Err(
                        error=StorageError.OPERATION_FAILED,
                        namespace="replay_store",
                        context_msg="Replay not found",
                    )

                return Ok(
                    ReplayMetadata(
                        id=ReplayId(row[0]),
                        maze_id=MazeId(row[1]),
                        started_at=row[2],
                        ended_at=row[3],
                        tick_hz=row[4],
                        level=row[5],
                        simulation_version=row[6],
                        config_hash=row[7],
                        rng_seed=row[8],
                    )
                )

            except Exception:
                return Err(
                    error=StorageError.QUERY_FAILED,
                    namespace="replay_store",
                    context_msg="Failed to load replay",
                )

        return self.transaction(select)

    def finish(
        self,
        replay_id: ReplayId,
    ) -> Result[None, StorageError]:
        """Mark a replay as finished."""

        def update(
            transaction: Transaction,
        ) -> Result[None, StorageError]:
            try:
                cursor = transaction.connection.execute(
                    FINISH_REPLAY,
                    (
                        int(time()),
                        int(replay_id),
                    ),
                )

                if cursor.rowcount == 0:
                    return Err(
                        error=StorageError.OPERATION_FAILED,
                        namespace="replay_store",
                        context_msg="Replay not found",
                    )

                return Ok(None)

            except Exception:
                return Err(
                    error=StorageError.QUERY_FAILED,
                    namespace="replay_store",
                    context_msg="Failed to finish replay",
                )

        return self.transaction(update)

    def append(
        self,
        batch: FrameBatch,
    ) -> Result[None, StorageError]:
        """Persist a batch of frames and world changes atomically."""

        def insert(
            transaction: Transaction,
        ) -> Result[None, StorageError]:
            try:
                frame_rows = tuple(
                    (
                        int(batch.replay_id),
                        int(frame.tick),
                        int(frame.player.position.x),
                        int(frame.player.position.y),
                        int(frame.player.direction),
                        int(frame.score),
                        frame.lives,
                        int(frame.phase),
                    )
                    for frame in batch.frames
                )
                ghost_rows = tuple(
                    (
                        int(batch.replay_id),
                        int(frame.tick),
                        int(ghost.ghost),
                        int(ghost.position.x),
                        int(ghost.position.y),
                        int(ghost.direction),
                        int(ghost.state),
                    )
                    for frame in batch.frames
                    for ghost in frame.ghosts
                )
                collectible_change_rows = tuple(
                    (
                        int(batch.replay_id),
                        int(change.tick),
                        int(change.tile),
                        int(change.collectible),
                    )
                    for change in batch.collectible_changes
                )

                _ = transaction.connection.executemany(
                    INSERT_FRAME, frame_rows
                )
                _ = transaction.connection.executemany(
                    INSERT_GHOST_FRAME,
                    ghost_rows,
                )
                _ = transaction.connection.executemany(
                    INSERT_COLLECTIBLE_CHANGE,
                    collectible_change_rows,
                )

                return Ok(None)

            except Exception:
                return Err(
                    error=StorageError.QUERY_FAILED,
                    namespace="replay_store",
                    context_msg="Failed to append replay batch",
                )

        return self.transaction(insert)

    def frame(
        self,
        replay_id: ReplayId,
        tick: Tick,
    ) -> Result[Frame, StorageError]:
        """Load a single frame."""

        def select(
            transaction: Transaction,
        ) -> Result[Frame, StorageError]:
            try:
                frame_row = cast(
                    "tuple[int, int, int, int, int, int] | None",
                    transaction.connection.execute(
                        SELECT_FRAME,
                        (int(replay_id), int(tick)),
                    ).fetchone(),
                )

                if frame_row is None:
                    return Err(
                        error=StorageError.OPERATION_FAILED,
                        namespace="replay_store",
                        context_msg="Frame not found",
                    )

                ghost_rows = cast(
                    "list[tuple[int, int, int, int, int]]",
                    transaction.connection.execute(
                        SELECT_GHOST_FRAMES,
                        (int(replay_id), int(tick)),
                    ).fetchall(),
                )
                ghosts = tuple(
                    GhostFrame(
                        ghost=Ghost(row[0]),
                        position=Position(
                            x=Coord(row[1]),
                            y=Coord(row[2]),
                        ),
                        direction=Direction(row[3]),
                        state=GhostState(row[4]),
                    )
                    for row in ghost_rows
                )

                return Ok(
                    Frame(
                        tick=tick,
                        player=PlayerFrame(
                            position=Position(
                                x=Coord(frame_row[0]),
                                y=Coord(frame_row[1]),
                            ),
                            direction=Direction(frame_row[2]),
                        ),
                        ghosts=ghosts,
                        score=Score(frame_row[3]),
                        lives=frame_row[4],
                        phase=GamePhase(frame_row[5]),
                    )
                )

            except Exception:
                return Err(
                    error=StorageError.QUERY_FAILED,
                    namespace="replay_store",
                    context_msg="Failed to load frame",
                )

        return self.transaction(select)

    def snapshot(
        self,
        replay_id: ReplayId,
        tick: Tick,
    ) -> Result[GameSnapshot, StorageError]:
        """Reconstruct complete game state at a simulation tick."""
        replay = self.replay(replay_id)
        if isinstance(replay, Err):
            return replay

        encoded_maze = self.maze(replay.value.maze_id)
        if isinstance(encoded_maze, Err):
            return encoded_maze

        frame = self.frame(replay_id, tick)
        if isinstance(frame, Err):
            return frame

        def reconstruct(
            transaction: Transaction,
        ) -> Result[GameSnapshot, StorageError]:
            try:
                changes = cast(
                    "list[tuple[int, int]]",
                    transaction.connection.execute(
                        SELECT_COLLECTIBLE_CHANGES,
                        (int(replay_id), int(tick)),
                    ).fetchall(),
                )
                collectibles = bytearray(
                    encoded_maze.value.initial_collectibles
                )

                for tile, collectible in changes:
                    byte_index = tile // 4
                    if byte_index >= len(collectibles):
                        return Err(
                            error=StorageError.OPERATION_FAILED,
                            namespace="replay_store",
                            context_msg="Collectible change is outside the maze",
                        )

                    shift = tile % 4 * 2
                    mask = 0b11 << shift
                    collectibles[byte_index] = (
                        collectibles[byte_index] & ~mask
                    ) | (collectible << shift)

                maze = Maze(
                    id=replay.value.maze_id,
                    width=encoded_maze.value.width,
                    height=encoded_maze.value.height,
                    topology=encoded_maze.value.topology,
                    initial_collectibles=encoded_maze.value.initial_collectibles,
                    checksum=encoded_maze.value.checksum,
                )

                return Ok(
                    GameSnapshot(
                        replay_id=replay_id,
                        tick=tick,
                        maze=maze,
                        player=frame.value.player,
                        ghosts=frame.value.ghosts,
                        collectibles=bytes(collectibles),
                        score=frame.value.score,
                        lives=frame.value.lives,
                        phase=frame.value.phase,
                    )
                )

            except Exception:
                return Err(
                    error=StorageError.QUERY_FAILED,
                    namespace="replay_store",
                    context_msg="Failed to reconstruct snapshot",
                )

        return self.transaction(reconstruct)


INSERT_MAZE = """
INSERT INTO maze (
    width,
    height,
    entry_x,
    entry_y,
    exit_x,
    exit_y,
    topology,
    initial_collectibles,
    checksum
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
RETURNING id
"""

SELECT_MAZE = """
select width, height, entry_x, entry_y, exit_x, exit_y, topology, initial_collectibles, checksum from maze where id = ?
"""

INSERT_REPLAY = """
insert into replay ( maze_id, started_at, tick_hz, level, simulation_version, config_hash, rng_seed) values (?, ?, ?, ?, ?, ?, ?) returning id
"""


SELECT_REPLAY = """
select id, maze_id, started_at, ended_at, tick_hz, level, simulation_version, config_hash, rng_seed from replay where id = ?
"""

FINISH_REPLAY = """
UPDATE replay
SET ended_at = ?
WHERE id = ?
"""

INSERT_FRAME = """
INSERT INTO frame (
    replay_id,
    tick,
    pac_x,
    pac_y,
    pac_dir,
    score,
    lives,
    phase
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_GHOST_FRAME = """
INSERT INTO ghost_frame (
    replay_id,
    tick,
    ghost,
    x,
    y,
    direction,
    state
)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""

INSERT_COLLECTIBLE_CHANGE = """
INSERT INTO collectible_change (
    replay_id,
    tick,
    tile,
    collectible
)
VALUES (?, ?, ?, ?)
"""

SELECT_FRAME = """
SELECT pac_x, pac_y, pac_dir, score, lives, phase
FROM frame
WHERE replay_id = ? AND tick = ?
"""

SELECT_GHOST_FRAMES = """
SELECT ghost, x, y, direction, state
FROM ghost_frame
WHERE replay_id = ? AND tick = ?
ORDER BY ghost
"""

SELECT_COLLECTIBLE_CHANGES = """
SELECT tile, collectible
FROM collectible_change
WHERE replay_id = ? AND tick <= ?
ORDER BY tick, tile
"""
