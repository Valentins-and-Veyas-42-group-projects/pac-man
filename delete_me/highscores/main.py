# uv run python delete_me/highscores/main.py
# Made by Codex as a disposable highscore integration runner.

"""Exercise highscore persistence through the public store boundary."""

from pathlib import Path
from tempfile import TemporaryDirectory

from pacman.highscores.store import HighscoreError, HighscoreStore
from pacman.models import HighscoreEntry
from typed_errs import Err, Ok, Result, catch_bubble


@catch_bubble
def run(database_path: Path) -> Result[None, HighscoreError]:
    """Persist, trim, reopen, and verify representative highscores.

    Args:
        database_path: Temporary SQLite database location.

    Returns:
        Success or the first typed highscore failure.
    """
    store = HighscoreStore(database_path)
    _ = store.initialize_highscores().q

    for score in range(12):
        _ = store.save(HighscoreEntry(f"Player {score}", score)).q

    scores = HighscoreStore(database_path).load_top(10).q
    expected = list(range(11, 1, -1))
    if [entry.score for entry in scores] != expected:
        return Err(
            HighscoreError.STORAGE_FAILED,
            namespace="highscores::integration",
            context_msg="Persisted top ten did not round-trip",
        )

    print("highscore roundtrip OK")
    print(f"scores: {[entry.score for entry in scores]}")
    return Ok(None)


def main() -> None:
    """Run the highscore integration against a temporary real database.

    Raises:
        SystemExit: When the integration check returns an error.
    """
    with TemporaryDirectory(prefix="pacman-highscores-") as directory:
        result = run(Path(directory) / "highscores.sqlite3")
        if isinstance(result, Err):
            result.print_diagnostic()
            raise SystemExit(1)


if __name__ == "__main__":
    main()
