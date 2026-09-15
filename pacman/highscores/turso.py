"""Backward-compatible name for the default Turso highscore store."""

from .store import HighscoreStore


class TursoHighscoreStore(HighscoreStore):
    """Preserve the explicit Turso class name for existing callers."""
