"""Optional Turso-backed replay persistence."""

from pathlib import Path

from sqlite_callback_store import StorageError, StoreOptions, TursoStore
from typed_errs import Result

from .store import ReplayStore, _schema


def _turso_schema() -> str:
    """Remove table options unsupported by Turso.

    Returns:
        Replay schema accepted by the Turso engine.
    """
    return (
        _schema()
        .replace(
            ") WITHOUT ROWID,\nSTRICT;",
            ");",
        )
        .replace(") STRICT;", ");")
    )


class TursoReplayStore(TursoStore, ReplayStore):
    """Persist replays with the Turso engine and optional cloud sync."""

    def __init__(
        self,
        path: str | Path,
        *,
        remote_url: str | None = None,
        auth_token: str | None = None,
        options: StoreOptions | None = None,
    ) -> None:
        """Configure local replay storage with optional Turso Cloud sync."""
        super().__init__(
            path,
            remote_url=remote_url,
            auth_token=auth_token,
            options=options,
        )

    def initialize_replay(self) -> Result[None, StorageError]:
        """Initialize the replay schema using Turso-compatible table syntax.

        Returns:
            Success or a typed storage failure.
        """
        return self.initialize(_turso_schema())
