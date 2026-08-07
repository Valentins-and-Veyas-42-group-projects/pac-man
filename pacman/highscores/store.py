"""Persistent highscore table (SQLite-backed).

Keeps the top 10 (name, score) rows. Player names are max 10
characters, alphanumeric and spaces only; scores are non-negative
integers, per the subject's highscore requirements. Robust to file
errors (missing file, corrupt database, etc.) -- callers get a
Result back instead of an exception bubbling up.
"""

import sqlite3
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Generator

from ..errors import Diagnostic, Err, Result
from ..models import HighscoreEntry


class HighscoreError(Enum):
    """Enumerate failure modes for the highscore store."""


def HighscoreErr(
    error: HighscoreError, diagnostic: Diagnostic | None = None
) -> Err[HighscoreError]:
    """Helper to bake module defaults into every highscore Err."""
    return Err(
        error=error,
        diagnostic=diagnostic,
        namespace="highscores::store",
        context_msg="Highscore persistence failed",
    )


class HighscoreStore:
    """Loads and saves the persistent top-10 highscore table."""

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection]:
        """Open a connection to the highscore database, ensuring the
        schema exists and the connection is closed afterward."""
        raise NotImplementedError
        yield  # pragma: no cover - keeps this a generator for mypy

    def load_top(
        self, limit: int
    ) -> Result[list[HighscoreEntry], HighscoreError]:
        """Load the top `limit` highscores, ordered by score
        descending."""
        raise NotImplementedError

    def save(
        self, entry: HighscoreEntry
    ) -> Result[None, HighscoreError]:
        """Validate and persist a new highscore entry."""
        raise NotImplementedError
