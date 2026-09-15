from pathlib import Path

from benchmarks.highscore_ingestion import compare_ingestion


def test_ingestion_benchmark_compares_complete_databases(tmp_path: Path) -> None:
    result = compare_ingestion(tmp_path, games=25, rounds=1)

    assert result.games == 25
    assert result.sqlite.games_per_second > 0
    assert result.turso.games_per_second > 0
    assert result.sqlite.persisted_games == 25
    assert result.turso.persisted_games == 25
