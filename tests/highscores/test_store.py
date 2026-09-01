"""Integration tests for persistent highscores."""

from pathlib import Path

import pytest
from pacman.highscores.store import HighscoreError, HighscoreStore
from pacman.models import HighscoreEntry
from typed_errs import Err, Some


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """Return a temporary database path."""
    return tmp_path / "scores" / "highscores.sqlite3"


def test_scores_persist_order_and_trim(database_path: Path) -> None:
    """A real database retains only its ten best scores across instances."""
    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()

    for score in range(12):
        store.save(HighscoreEntry(name=f"Player {score}", score=score)).unwrap()

    reopened = HighscoreStore(database_path)
    entries = reopened.load_top(10).unwrap()
    assert [entry.score for entry in entries] == list(range(11, 1, -1))
    assert len(entries) == 10


def test_load_top_honors_smaller_limit(database_path: Path) -> None:
    """Callers can request fewer than the stored top ten."""
    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()
    store.save(HighscoreEntry("First", 20)).unwrap()
    store.save(HighscoreEntry("Second", 10)).unwrap()

    assert store.load_top(1).unwrap() == [HighscoreEntry("First", 20)]
    assert store.load_top(0).unwrap() == []


@pytest.mark.parametrize("name", ["", "           ", "too-long-name", "bad_name"])
def test_invalid_names_return_diagnostics(database_path: Path, name: str) -> None:
    """Invalid player names remain inside the typed diagnostic boundary."""
    result = HighscoreStore(database_path).save(HighscoreEntry(name, 42))
    assert isinstance(result, Err)
    assert result.error == HighscoreError.INVALID_NAME
    assert isinstance(result.diagnostic, Some)


@pytest.mark.parametrize("score", [-1, True])
def test_invalid_scores_return_diagnostics(database_path: Path, score: int) -> None:
    """Negative and boolean scores are rejected before storage."""
    result = HighscoreStore(database_path).save(HighscoreEntry("Player", score))
    assert isinstance(result, Err)
    assert result.error == HighscoreError.INVALID_SCORE
    assert isinstance(result.diagnostic, Some)


def test_uninitialized_store_returns_storage_diagnostic(database_path: Path) -> None:
    """A missing schema produces a useful error instead of an exception."""
    result = HighscoreStore(database_path).load_top(10)
    assert isinstance(result, Err)
    assert result.error == HighscoreError.STORAGE_FAILED
    assert isinstance(result.diagnostic, Some)
