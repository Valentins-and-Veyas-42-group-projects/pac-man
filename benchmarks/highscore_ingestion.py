"""Measure verified attributed-game ingestion with local Turso."""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from pacman.highscores.store import HighscoreStore
from pacman.models import HighscoreEntry


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Median ingestion result from verified fresh Turso databases."""

    seconds: float
    games_per_second: float
    persisted_games: int
    verified_players: int


def benchmark_ingestion(
    root: Path,
    *,
    games: int = 10_000,
    rounds: int = 5,
) -> IngestionResult:
    """Benchmark attributed-game batches on fresh local Turso databases.

    Returns:
        Median throughput plus persisted game/player verification totals.

    Raises:
        ValueError: If the workload or repeat count is not positive.
        RuntimeError: If a round loses game or player attribution data.
    """
    if games <= 0 or rounds <= 0:
        raise ValueError("games and rounds must be positive")

    root.mkdir(parents=True, exist_ok=True)
    player_count = min(games, 100)
    entries = [HighscoreEntry(f"P{index % player_count}", index) for index in range(games)]
    elapsed: list[float] = []
    persisted_games = 0
    verified_players = 0

    for round_number in range(rounds):
        path = root / f"turso-{round_number}.db"
        _remove_database(path)
        store = HighscoreStore(path)
        store.initialize_highscores().unwrap()

        started = perf_counter()
        store.save_many(entries).unwrap()
        elapsed.append(perf_counter() - started)

        persisted_games = store.game_count().unwrap()
        verified_players = sum(
            store.player_game_count(f"P{index}").unwrap()
            for index in range(player_count)
        )
        if persisted_games != games or verified_players != games:
            raise RuntimeError(
                "Turso attribution verification failed: "
                f"games={persisted_games}/{games}, players={verified_players}/{games}"
            )

    duration = median(elapsed)
    return IngestionResult(
        seconds=duration,
        games_per_second=games / duration,
        persisted_games=persisted_games,
        verified_players=verified_players,
    )


def _remove_database(path: Path) -> None:
    """Remove a prior benchmark database and its transient sidecars."""
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        candidate.unlink(missing_ok=True)


def main() -> None:
    """Run and print a local Turso ingestion benchmark."""
    parser = ArgumentParser()
    parser.add_argument("--games", type=int, default=10_000)
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="pacman-highscore-benchmark-") as directory:
        result = benchmark_ingestion(Path(directory), games=args.games, rounds=args.rounds)
    print(f"games={args.games} rounds={args.rounds}")
    print(
        f"turso: {result.seconds:.6f}s "
        f"({result.games_per_second:,.0f} games/s, "
        f"{result.verified_players:,} attributed)"
    )


if __name__ == "__main__":
    main()
