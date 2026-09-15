"""Compare attributed-game ingestion with SQLite and local Turso."""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from pacman.highscores.store import HighscoreStore, SQLiteHighscoreStore
from pacman.models import HighscoreEntry


@dataclass(frozen=True, slots=True)
class EngineResult:
    """Median ingestion result for one database engine."""

    seconds: float
    games_per_second: float
    persisted_games: int


@dataclass(frozen=True, slots=True)
class Comparison:
    """Comparable local results produced from the same workload."""

    games: int
    rounds: int
    sqlite: EngineResult
    turso: EngineResult


def _measure(
    store_type: type[HighscoreStore] | type[SQLiteHighscoreStore],
    root: Path,
    name: str,
    entries: list[HighscoreEntry],
    rounds: int,
) -> EngineResult:
    """Measure fresh-database bulk ingestion and verify every round.

    Returns:
        Median verified throughput for the selected engine.

    Raises:
        RuntimeError: If an engine does not persist the complete batch.
    """
    elapsed: list[float] = []
    persisted = 0
    for round_number in range(rounds):
        path = root / f"{name}-{round_number}.db"
        store = store_type(path)
        store.initialize_highscores().unwrap()
        started = perf_counter()
        store.save_many(entries).unwrap()
        elapsed.append(perf_counter() - started)
        persisted = store.game_count().unwrap()
        if persisted != len(entries):
            raise RuntimeError(f"{name} persisted {persisted}/{len(entries)} games")
    duration = median(elapsed)
    return EngineResult(duration, len(entries) / duration, persisted)


def compare_ingestion(root: Path, *, games: int = 10_000, rounds: int = 5) -> Comparison:
    """Benchmark equal attributed-game batches on fresh local databases.

    Returns:
        Verified median results for standard SQLite and local Turso.

    Raises:
        ValueError: If the workload or repeat count is not positive.
    """
    if games <= 0 or rounds <= 0:
        raise ValueError("games and rounds must be positive")
    root.mkdir(parents=True, exist_ok=True)
    entries = [HighscoreEntry(f"P{index % 100}", index) for index in range(games)]
    return Comparison(
        games=games,
        rounds=rounds,
        sqlite=_measure(SQLiteHighscoreStore, root, "sqlite", entries, rounds),
        turso=_measure(HighscoreStore, root, "turso", entries, rounds),
    )


def main() -> None:
    """Run and print a local engine comparison."""
    parser = ArgumentParser()
    parser.add_argument("--games", type=int, default=10_000)
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="pacman-highscore-benchmark-") as directory:
        result = compare_ingestion(Path(directory), games=args.games, rounds=args.rounds)
    print(f"games={result.games} rounds={result.rounds}")
    print(
        f"sqlite: {result.sqlite.seconds:.6f}s "
        f"({result.sqlite.games_per_second:,.0f} games/s)"
    )
    print(
        f"turso:  {result.turso.seconds:.6f}s "
        f"({result.turso.games_per_second:,.0f} games/s)"
    )


if __name__ == "__main__":
    main()
