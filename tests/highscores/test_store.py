"""Integration tests for persistent highscores."""

import sqlite3
from pathlib import Path

import pytest
from pacman.highscores.store import HighscoreError, HighscoreStore, SQLiteHighscoreStore
from pacman.highscores.turso import TursoHighscoreStore
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


def test_turso_highscores_use_the_existing_store_contract(database_path: Path) -> None:
    """The optional Turso adapter persists and orders real scores."""
    pytest.importorskip("turso")
    store = TursoHighscoreStore(database_path)
    store.initialize_highscores().unwrap()
    store.save(HighscoreEntry("Veya", 42)).unwrap()

    assert store.load_top(10).unwrap() == [HighscoreEntry("Veya", 42)]


def test_default_store_uses_turso_with_a_sqlite_compatible_file(database_path: Path) -> None:
    """The default engine is Turso while its local database remains SQLite compatible."""
    pytest.importorskip("turso")
    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()
    store.save(HighscoreEntry("Veya", 42)).unwrap()

    sqlite_store = SQLiteHighscoreStore(database_path)
    assert sqlite_store.load_top(10).unwrap() == [HighscoreEntry("Veya", 42)]
    with sqlite3.connect(database_path) as connection:
        views = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            )
        }
        assert views >= {"global_highscores", "player_highscores"}
        foreign_keys = connection.execute("PRAGMA foreign_key_list(game)").fetchall()
        assert [(row[2], row[3]) for row in foreign_keys] == [("player", "player_id")]


def test_legacy_top_ten_rows_migrate_to_attributed_games(database_path: Path) -> None:
    """Existing SQLite highscores survive the normalized Turso-first schema."""
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE highscores (id INTEGER PRIMARY KEY, name TEXT, score INTEGER)"
        )
        connection.execute(
            "INSERT INTO highscores(name, score) VALUES (?, ?)",
            ("Veya", 99),
        )

    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()
    store.initialize_highscores().unwrap()

    assert store.load_global(10).unwrap() == [HighscoreEntry("Veya", 99)]
    assert store.player_game_count("Veya").unwrap() == 1


def test_each_game_belongs_to_exactly_one_player(database_path: Path) -> None:
    """Every persisted game has one non-null player foreign key."""
    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()
    store.save(HighscoreEntry("Veya", 20)).unwrap()
    store.save(HighscoreEntry("Veya", 10)).unwrap()
    store.save(HighscoreEntry("Tino", 30)).unwrap()

    assert store.game_count().unwrap() == 3
    assert store.player_game_count("Veya").unwrap() == 2
    assert store.player_game_count("Tino").unwrap() == 1


def test_global_and_per_player_highscore_views(database_path: Path) -> None:
    """Global and player-scoped views rank the same attributed games."""
    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()
    for entry in (
        HighscoreEntry("Veya", 20),
        HighscoreEntry("Tino", 30),
        HighscoreEntry("Veya", 40),
    ):
        store.save(entry).unwrap()

    assert store.load_global(10).unwrap() == [
        HighscoreEntry("Veya", 40),
        HighscoreEntry("Tino", 30),
        HighscoreEntry("Veya", 20),
    ]
    assert store.load_player("Veya", 10).unwrap() == [
        HighscoreEntry("Veya", 40),
        HighscoreEntry("Veya", 20),
    ]


def test_sqlite_and_turso_bulk_ingestion_share_the_contract(database_path: Path) -> None:
    """Both engines ingest batches and expose identical rankings."""
    entries = [HighscoreEntry(f"P{i % 10}", i) for i in range(100)]
    turso = HighscoreStore(database_path.with_name("turso.db"))
    sqlite = SQLiteHighscoreStore(database_path.with_name("sqlite.db"))

    for store in (turso, sqlite):
        store.initialize_highscores().unwrap()
        store.save_many(entries).unwrap()

    assert turso.load_global(10).unwrap() == sqlite.load_global(10).unwrap()
    assert turso.game_count().unwrap() == sqlite.game_count().unwrap() == 100
