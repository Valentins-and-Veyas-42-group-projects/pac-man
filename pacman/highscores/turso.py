"""Optional Turso-backed highscore persistence."""

from sqlite_callback_store import TursoStore

from .store import HighscoreStore


class TursoHighscoreStore(TursoStore, HighscoreStore):
    """Persist highscores with the Turso engine and optional cloud sync."""
