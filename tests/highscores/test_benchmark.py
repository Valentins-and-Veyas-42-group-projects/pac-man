from pathlib import Path

from benchmarks.highscore_ingestion import benchmark_ingestion


def test_ingestion_benchmark_is_repeatable_and_verifies_attribution(tmp_path: Path) -> None:
    first = benchmark_ingestion(tmp_path, games=25, rounds=1)
    second = benchmark_ingestion(tmp_path, games=25, rounds=1)

    for result in (first, second):
        assert result.games_per_second > 0
        assert result.persisted_games == 25
        assert result.verified_attributions == 25
