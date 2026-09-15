"""Apply ordered SQL migrations to the Turso highscore database."""

import sqlite3
from collections.abc import Callable
from importlib.resources import files
from typing import Protocol, TypeVar, cast

from sqlite_callback_store import StorageError
from typed_errs import Err, Ok, Result

T = TypeVar("T")

_MIGRATION_PACKAGE = "pacman.highscores.migrations"
_BOOTSTRAP_FILE = "000_schema_migrations.sql"
_MIGRATION_FILES = ("001_normalize_player_games.sql",)


class MigrationStore(Protocol):
    """Storage operations required by the migration runner."""

    def initialize(self, schema: str) -> Result[None, StorageError]:
        """Execute one schema or migration script."""
        ...

    def read(
        self,
        operation: Callable[[sqlite3.Connection], Result[T, StorageError]],
    ) -> Result[T, StorageError]:
        """Run a read callback against the migration database."""
        ...


def apply_migrations(store: MigrationStore) -> Result[None, StorageError]:
    """Apply every unapplied SQL migration in version order.

    Each migration owns an explicit transaction and records its version in the
    same commit as its schema/data changes.

    Returns:
        Success, or the first storage/resource failure.
    """
    bootstrap = _read_sql(_BOOTSTRAP_FILE)
    if isinstance(bootstrap, Err):
        return bootstrap
    initialized = store.initialize(bootstrap.value)
    if isinstance(initialized, Err):
        return initialized

    applied = store.read(_load_applied_versions)
    if isinstance(applied, Err):
        return applied

    for filename in _MIGRATION_FILES:
        version = int(filename.split("_", maxsplit=1)[0])
        if version in applied.value:
            continue
        sql = _read_sql(filename)
        if isinstance(sql, Err):
            return sql
        migrated = store.initialize(sql.value)
        if isinstance(migrated, Err):
            refreshed = store.read(_load_applied_versions)
            if not isinstance(refreshed, Err) and version in refreshed.value:
                continue
            return migrated

    return Ok(None)


def _read_sql(filename: str) -> Result[str, StorageError]:
    try:
        return Ok(files(_MIGRATION_PACKAGE).joinpath(filename).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        return Err(
            StorageError.SCHEMA_FAILED,
            namespace="highscores::migrations",
            context_msg=f"Could not read migration {filename}: {error}",
        )


def _load_applied_versions(connection: sqlite3.Connection) -> Result[frozenset[int], StorageError]:
    rows = cast(
        "list[sqlite3.Row | tuple[int]]",
        connection.execute("SELECT version FROM schema_migrations").fetchall(),
    )
    return Ok(frozenset(cast(int, row[0]) for row in rows))
