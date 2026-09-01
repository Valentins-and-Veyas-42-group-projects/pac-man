"""Persistent highscore table (SQLite-backed).

Keeps the top 10 (name, score) rows. Player names are max 10
characters, alphanumeric and spaces only; scores are non-negative
integers, per the subject's highscore requirements. Robust to file
errors (missing file, corrupt database, etc.) -- callers get a
Result back instead of an exception bubbling up.
"""

import sqlite3
from enum import Enum
from pathlib import Path
from typing import cast

from python_crimes import pipe
from sqlite_callback_store import SQLiteStore, StorageError, Transaction
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
"""

INSERT_HIGHSCORE = "INSERT INTO highscores(name, score) VALUES (?, ?)"
TRIM_HIGHSCORES = """
DELETE FROM highscores
WHERE id NOT IN (
    SELECT id FROM highscores ORDER BY score DESC, id ASC LIMIT 10
)
"""
SELECT_HIGHSCORES = """
SELECT name, score FROM highscores
ORDER BY score DESC, id ASC
LIMIT ?
"""


class HighscoreStore(SQLiteStore):
    """Loads and saves the persistent top-10 highscore table."""

    def __init__(self, db_path: str | Path) -> None:
        """Create a store for the given database path."""
        super().__init__(db_path)

    @catch_bubble
    def initialize_highscores(self) -> Result[None, HighscoreError]:
        """Create the highscore table when it does not exist.

        Returns:
            Success or a diagnosed storage failure.
        """
        _ = (
            self
            .initialize(SCHEMA)
            .map_err_with(_storage_err.with_(operation="initialize the highscore database"))
            .q
        )
        return Ok(None)

    @catch_bubble
    def load_top(self, limit: int) -> Result[list[HighscoreEntry], HighscoreError]:
        """Load the top `limit` highscores, ordered by score descending.

        Returns:
            Ordered entries or a diagnosed validation or storage failure.
        """

        def select(
            connection: sqlite3.Connection,
            valid_limit: int,
        ) -> Result[list[HighscoreEntry], StorageError]:
            rows = cast(
                "list[sqlite3.Row]",
                connection.execute(SELECT_HIGHSCORES, (valid_limit,)).fetchall(),
            )
            return Ok([
                HighscoreEntry(
                    name=cast(str, row["name"]),
                    score=cast(int, row["score"]),
                )
                for row in rows
            ])

        valid_limit = (limit @ _validate_limit).q
        entries = (
            self
            .read(lambda connection: select(connection, valid_limit))
            .map_err_with(_storage_err.with_(operation="load highscores"))
            .q
        )
        return Ok(entries)

    @catch_bubble
    def save(self, entry: HighscoreEntry) -> Result[None, HighscoreError]:
        """Validate and persist a new highscore entry.

        Returns:
            Success or a diagnosed validation or storage failure.
        """

        def insert(transaction: Transaction) -> Result[None, StorageError]:
            _ = transaction.connection.execute(
                INSERT_HIGHSCORE,
                (valid_entry.name, valid_entry.score),
            )
            _ = transaction.connection.execute(TRIM_HIGHSCORES)
            return Ok(None)

        valid_entry = (entry @ _validate_entry).q
        _ = (
            self
            .transaction(insert)
            .map_err_with(_storage_err.with_(operation="save the highscore"))
            .q
        )
        return Ok(None)


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
        The valid limit or a diagnosed validation failure.
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
def _validate_entry(
    entry: HighscoreEntry,
) -> Result[HighscoreEntry, HighscoreError]:
    """Validate a highscore at the persistence boundary.

    Returns:
        The valid entry or a diagnosed validation failure.
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

    if isinstance(entry.score, bool) or entry.score < 0:
        return HighscoreErr(
            HighscoreError.INVALID_SCORE,
            entry.score,
            "Use a non-negative integer score.",
            "Invalid player score",
        )

    return Ok(entry)
