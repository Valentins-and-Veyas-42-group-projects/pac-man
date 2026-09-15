"""Turso-first highscore persistence with SQLite-compatible storage."""

import sqlite3
from collections.abc import Callable, Iterable
from enum import Enum
from pathlib import Path
from time import time
from typing import Protocol, TypeVar, cast

from python_crimes import pipe
from sqlite_callback_store import SQLiteStore, StorageError, StoreOptions, Transaction, TursoStore
from typed_errs import Diagnostic, Err, Ok, Result, Some, catch_bubble

from pacman.models import HighscoreEntry


class HighscoreError(Enum):
    """Enumerate failure modes for the highscore store."""

    INVALID_NAME = "invalid_name"
    INVALID_SCORE = "invalid_score"
    INVALID_LIMIT = "invalid_limit"
    STORAGE_FAILED = "storage_failed"


def HighscoreErr(
    error: HighscoreError,
    value: object,
    help_msg: str,
    context_msg: str,
) -> Err[HighscoreError]:
    """Bake module defaults into a highscore error.

    Returns:
        A highscore error with a printable diagnostic.
    """
    rendered = str(value)
    return Err(
        error=error,
        diagnostic=Some(
            Diagnostic(
                filename="highscores",
                line_num=1,
                line_text=rendered,
                col_start=0,
                col_end=max(1, len(rendered)),
                help_msg=Some(help_msg),
            )
        ),
        namespace="highscores::store",
        context_msg=context_msg,
    )


SCHEMA = """
CREATE TABLE IF NOT EXISTS highscores (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score >= 0)
);

CREATE TABLE IF NOT EXISTS highscore_migration (
    name TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS player (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    CHECK (length(name) BETWEEN 1 AND 10)
);

CREATE TABLE IF NOT EXISTS game (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES player(id),
    score INTEGER NOT NULL CHECK (score >= 0),
    played_at INTEGER NOT NULL
);

INSERT OR IGNORE INTO player(name)
SELECT DISTINCT name FROM highscores
WHERE NOT EXISTS (
    SELECT 1 FROM highscore_migration WHERE name = 'legacy-highscores-v1'
);

INSERT INTO game(player_id, score, played_at)
SELECT player.id, highscores.score, 0
FROM highscores JOIN player ON player.name = highscores.name
WHERE NOT EXISTS (
    SELECT 1 FROM highscore_migration WHERE name = 'legacy-highscores-v1'
);

INSERT OR IGNORE INTO highscore_migration(name) VALUES ('legacy-highscores-v1');
DROP TABLE highscores;

CREATE INDEX IF NOT EXISTS game_global_score_idx
ON game(score DESC, id ASC);
CREATE INDEX IF NOT EXISTS game_player_score_idx
ON game(player_id, score DESC, id ASC);

DROP VIEW IF EXISTS global_highscores;
CREATE VIEW global_highscores AS
SELECT
    game.id AS game_id,
    player.id AS player_id,
    player.name AS name,
    game.score AS score,
    game.played_at AS played_at
FROM game JOIN player ON player.id = game.player_id;

DROP VIEW IF EXISTS player_highscores;
CREATE VIEW player_highscores AS
SELECT
    game.id AS game_id,
    player.id AS player_id,
    player.name AS name,
    game.score AS score,
    game.played_at AS played_at,
    ROW_NUMBER() OVER (
        PARTITION BY player.id ORDER BY game.score DESC, game.id ASC
    ) AS player_rank
FROM game JOIN player ON player.id = game.player_id;
"""

INSERT_PLAYER = "INSERT INTO player(name) VALUES (?) ON CONFLICT(name) DO NOTHING"
SELECT_PLAYER_ID = "SELECT id FROM player WHERE name = ? COLLATE NOCASE"
INSERT_GAME = "INSERT INTO game(player_id, score, played_at) VALUES (?, ?, ?)"
SELECT_GLOBAL = """
SELECT name, score FROM global_highscores
ORDER BY score DESC, game_id ASC
LIMIT ?
"""
SELECT_PLAYER = """
SELECT name, score FROM player_highscores
WHERE name = ? COLLATE NOCASE
ORDER BY player_rank ASC
LIMIT ?
"""

T = TypeVar("T")


class _Store(Protocol):
    """Structural storage API used by both database engines."""

    def initialize(self, schema: str) -> Result[None, StorageError]: ...

    def read(
        self,
        operation: Callable[[sqlite3.Connection], Result[T, StorageError]],
    ) -> Result[T, StorageError]: ...

    def transaction(
        self,
        operation: Callable[[Transaction], Result[T, StorageError]],
    ) -> Result[T, StorageError]: ...


class _HighscoreOperations:
    """Engine-independent highscore queries and writes."""

    @property
    def _store(self) -> _Store:
        return cast(_Store, self)

    @catch_bubble
    def initialize_highscores(self) -> Result[None, HighscoreError]:
        """Create or migrate the player, game, and leaderboard schema.

        Returns:
            Success or a diagnosed storage failure.
        """
        _ = (
            self._store.initialize(SCHEMA)
            .map_err_with(_storage_err.with_(operation="initialize the highscore database"))
            .q
        )
        return Ok(None)

    @catch_bubble
    def load_top(self, limit: int) -> Result[list[HighscoreEntry], HighscoreError]:
        """Load the global top scores for subject-compatible callers.

        Returns:
            Ordered entries or a validation/storage failure.
        """
        return self.load_global(limit)

    @catch_bubble
    def load_global(self, limit: int) -> Result[list[HighscoreEntry], HighscoreError]:
        """Load the global leaderboard ordered by score descending.

        Returns:
            Ordered global entries or a validation/storage failure.
        """
        valid_limit = (limit @ _validate_limit).q
        entries = (
            self._store.read(lambda connection: _select_entries(connection, SELECT_GLOBAL, (valid_limit,)))
            .map_err_with(_storage_err.with_(operation="load global highscores"))
            .q
        )
        return Ok(cast(list[HighscoreEntry], entries))

    @catch_bubble
    def load_player(self, name: str, limit: int) -> Result[list[HighscoreEntry], HighscoreError]:
        """Load one player's best games without mixing in other players.

        Returns:
            Ordered player entries or a validation/storage failure.
        """
        valid_name = (HighscoreEntry(name, 0) @ _validate_entry).q.name
        valid_limit = (limit @ _validate_limit).q
        entries = (
            self._store.read(
                lambda connection: _select_entries(
                    connection,
                    SELECT_PLAYER,
                    (valid_name, valid_limit),
                )
            )
            .map_err_with(_storage_err.with_(operation="load player highscores"))
            .q
        )
        return Ok(cast(list[HighscoreEntry], entries))

    @catch_bubble
    def save(self, entry: HighscoreEntry) -> Result[None, HighscoreError]:
        """Persist one game attributed to exactly one validated player.

        Returns:
            Success or a validation/storage failure.
        """
        _ = self.save_many((entry,)).q
        return Ok(None)

    @catch_bubble
    def save_many(self, entries: Iterable[HighscoreEntry]) -> Result[None, HighscoreError]:
        """Persist multiple attributed games in one transaction.

        Returns:
            Success or the first validation/storage failure.
        """
        validated = tuple((entry @ _validate_entry).q for entry in entries)
        played_at = int(time())

        def insert(transaction: Transaction) -> Result[None, StorageError]:
            players: dict[str, int] = {}
            game_rows: list[tuple[int, int, int]] = []
            for entry in validated:
                player_key = entry.name.casefold()
                player_id = players.get(player_key)
                if player_id is None:
                    _ = transaction.connection.execute(INSERT_PLAYER, (entry.name,))
                    row = cast(
                        "sqlite3.Row | tuple[int] | None",
                        transaction.connection.execute(SELECT_PLAYER_ID, (entry.name,)).fetchone(),
                    )
                    if row is None:
                        return Err(
                            StorageError.OPERATION_FAILED,
                            namespace="highscores::store",
                            context_msg="Player insert returned no identifier",
                        )
                    player_id = cast(int, row[0])
                    players[player_key] = player_id
                game_rows.append((player_id, entry.score, played_at))

            _ = transaction.connection.executemany(INSERT_GAME, game_rows)
            return Ok(None)

        _ = (
            self._store.transaction(insert)
            .map_err_with(_storage_err.with_(operation="save highscore games"))
            .q
        )
        return Ok(None)

    @catch_bubble
    def game_count(self) -> Result[int, HighscoreError]:
        """Return the number of persisted games."""
        count = (
            self._store.read(lambda connection: _select_count(connection, "SELECT COUNT(*) FROM game", ()))
            .map_err_with(_storage_err.with_(operation="count highscore games"))
            .q
        )
        return Ok(cast(int, count))

    @catch_bubble
    def player_game_count(self, name: str) -> Result[int, HighscoreError]:
        """Return the number of games attributed to one player."""
        valid_name = (HighscoreEntry(name, 0) @ _validate_entry).q.name
        count = (
            self._store.read(
                lambda connection: _select_count(
                    connection,
                    """
                    SELECT COUNT(*) FROM game
                    JOIN player ON player.id = game.player_id
                    WHERE player.name = ? COLLATE NOCASE
                    """,
                    (valid_name,),
                )
            )
            .map_err_with(_storage_err.with_(operation="count player games"))
            .q
        )
        return Ok(cast(int, count))


class HighscoreStore(_HighscoreOperations, TursoStore):
    """Default Turso engine with local SQLite-compatible persistence."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        remote_url: str | None = None,
        auth_token: str | None = None,
        options: StoreOptions | None = None,
    ) -> None:
        """Configure local Turso storage with optional cloud sync."""
        TursoStore.__init__(
            self,
            db_path,
            remote_url=remote_url,
            auth_token=auth_token,
            options=options,
        )


class SQLiteHighscoreStore(_HighscoreOperations, SQLiteStore):
    """Explicit CPython SQLite fallback sharing the same schema and API."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        options: StoreOptions | None = None,
    ) -> None:
        """Configure the standard-library SQLite engine."""
        SQLiteStore.__init__(self, db_path, options=options)


def _select_entries(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...],
) -> Result[list[HighscoreEntry], StorageError]:
    rows = cast("list[sqlite3.Row]", connection.execute(query, parameters).fetchall())
    return Ok([HighscoreEntry(name=cast(str, row["name"]), score=cast(int, row["score"])) for row in rows])


def _select_count(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...],
) -> Result[int, StorageError]:
    row = cast("sqlite3.Row | tuple[int] | None", connection.execute(query, parameters).fetchone())
    if row is None:
        return Err(
            StorageError.OPERATION_FAILED,
            namespace="highscores::store",
            context_msg="Count query returned no row",
        )
    return Ok(cast(int, row[0]))


@pipe
def _storage_err(
    error: Err[StorageError],
    operation: str,
) -> Err[HighscoreError]:
    """Translate a storage failure into the highscore error domain.

    Returns:
        A diagnosed highscore storage failure.
    """
    detail = error.context_msg or error.error.name.lower().replace("_", " ")
    return HighscoreErr(
        HighscoreError.STORAGE_FAILED,
        detail,
        "Check that the database path is writable and contains a valid SQLite database.",
        f"Could not {operation}",
    )


@pipe
def _validate_limit(limit: int) -> Result[int, HighscoreError]:
    """Validate a requested highscore count.

    Returns:
        The accepted limit or a validation failure.
    """
    if isinstance(limit, bool) or not 0 <= limit <= 10:
        return HighscoreErr(
            HighscoreError.INVALID_LIMIT,
            limit,
            "Use an integer from 0 through 10.",
            "Invalid highscore limit",
        )
    return Ok(limit)


@pipe
def _validate_entry(entry: HighscoreEntry) -> Result[HighscoreEntry, HighscoreError]:
    """Validate a highscore at the persistence boundary.

    Returns:
        The accepted entry or a validation failure.
    """
    if (
        not entry.name
        or len(entry.name) > 10
        or not any(character.isalnum() for character in entry.name)
        or any(not character.isalnum() and character != " " for character in entry.name)
    ):
        return HighscoreErr(
            HighscoreError.INVALID_NAME,
            entry.name,
            "Use 1 to 10 characters containing only letters, numbers, and spaces.",
            "Invalid player name",
        )

    if isinstance(entry.score, bool) or not isinstance(entry.score, int) or entry.score < 0:
        return HighscoreErr(
            HighscoreError.INVALID_SCORE,
            entry.score,
            "Use a non-negative integer score.",
            "Invalid player score",
        )

    return Ok(entry)
