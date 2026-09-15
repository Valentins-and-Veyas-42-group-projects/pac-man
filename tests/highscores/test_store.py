"""Integration tests for persistent highscores."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pacman.highscores.store import HighscoreError, HighscoreStore
from pacman.highscores.turso import TursoHighscoreStore
from pacman.models import HighscoreEntry
from typed_errs import Err, Ok, Some


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


def test_default_store_uses_turso_and_versioned_sql_migrations(database_path: Path) -> None:
    """The only engine is Turso and its migrations are recorded in the database."""
    pytest.importorskip("turso")
    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()
    store.save(HighscoreEntry("Veya", 42)).unwrap()

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
        migrations = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert migrations == [(1, "normalize-player-games")]
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'highscores'"
        ).fetchone() == (0,)


def test_concurrent_initialization_is_idempotent(database_path: Path) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(
                lambda _: HighscoreStore(database_path).initialize_highscores(),
                range(2),
            )
        )

    assert all(isinstance(result, Ok) for result in results)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone() == (1,)


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


def test_failed_legacy_migration_is_atomic_and_preserves_source(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE highscores (id INTEGER PRIMARY KEY, name TEXT, score INTEGER)")
        connection.execute("INSERT INTO highscores(name, score) VALUES (NULL, 99)")

    result = HighscoreStore(database_path).initialize_highscores()

    assert isinstance(result, Err)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM highscores").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone() == (0,)


def test_migration_rejects_an_existing_game_table_without_player_invariant(
    database_path: Path,
) -> None:
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE player (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute(
            "CREATE TABLE game (id INTEGER PRIMARY KEY, player_id INTEGER, score INTEGER, played_at INTEGER)"
        )
        connection.execute("INSERT INTO game(player_id, score, played_at) VALUES (NULL, 99, 0)")

    result = HighscoreStore(database_path).initialize_highscores()

    assert isinstance(result, Err)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM game WHERE player_id IS NULL").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone() == (0,)


def test_migration_rebuilds_valid_preexisting_tables_with_foreign_key(
    database_path: Path,
) -> None:
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE player (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute(
            "CREATE TABLE game (id INTEGER PRIMARY KEY, player_id INTEGER, score INTEGER, played_at INTEGER)"
        )
        connection.execute("INSERT INTO player(id, name) VALUES (1, 'Veya')")
        connection.execute("INSERT INTO game(player_id, score, played_at) VALUES (1, 99, 0)")

    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()

    assert store.game_count().unwrap() == 1
    invalid = store.transaction(
        lambda transaction: Ok(
            transaction.connection.execute(
                "INSERT INTO game(player_id, score, played_at) VALUES (?, ?, ?)",
                (999, 1, 0),
            )
        )
    )
    assert isinstance(invalid, Err)


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


def test_turso_bulk_ingestion_preserves_every_attributed_game(database_path: Path) -> None:
    """Turso ingests batches and exposes complete rankings."""
    entries = [HighscoreEntry(f"P{i % 10}", i) for i in range(100)]
    turso = HighscoreStore(database_path)
    turso.initialize_highscores().unwrap()
    turso.save_many(entries).unwrap()

    assert turso.game_count().unwrap() == 100
    assert turso.player_game_count("P0").unwrap() == 10


def test_turso_bulk_ingestion_handles_empty_and_large_batches(database_path: Path) -> None:
    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()

    store.save_many(()).unwrap()
    store.save_many(tuple(HighscoreEntry(f"P{i % 11}", i) for i in range(1_501))).unwrap()

    assert store.game_count().unwrap() == 1_501


def test_unicode_player_names_use_exact_consistent_identity(database_path: Path) -> None:
    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()
    store.save_many((HighscoreEntry("Straße", 10), HighscoreEntry("STRASSE", 20))).unwrap()

    assert store.player_game_count("Straße").unwrap() == 1
    assert store.player_game_count("STRASSE").unwrap() == 1
    assert store.load_player("Straße", 10).unwrap() == [HighscoreEntry("Straße", 10)]


def test_turso_connections_enforce_game_player_foreign_key(database_path: Path) -> None:
    store = HighscoreStore(database_path)
    store.initialize_highscores().unwrap()

    result = store.transaction(
        lambda transaction: Ok(
            transaction.connection.execute(
                "INSERT INTO game(player_id, score, played_at) VALUES (?, ?, ?)",
                (999, 10, 0),
            )
        )
    )

    assert isinstance(result, Err)
    assert store.game_count().unwrap() == 0
