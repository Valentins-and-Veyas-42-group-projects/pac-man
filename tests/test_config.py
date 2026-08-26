"""Focused tests for configuration loading."""

from pathlib import Path

from pacman.config import ConfigError, load_config, strip_json_comments
from typed_errs import Err, Some

FIXTURES = Path(__file__).parents[1] / "delete_me" / "config" / "fixtures"


def test_strip_json_comments_preserves_lines_and_hashes_in_strings() -> None:
    """Only full-line comments are blanked without shifting diagnostics."""
    source = '# comment\n{"name": "score-#1"}\n  # another'
    assert strip_json_comments(source) == '\n{"name": "score-#1"}\n'


def test_valid_config_loads_comments_and_levels() -> None:
    """The real valid fixture loads through file I/O and normalization."""
    config = load_config(str(FIXTURES / "valid.json")).unwrap()
    assert config.highscore_filename == "scores-#1.db"
    assert len(config.levels) == 2


def test_invalid_fields_recover_with_diagnostics() -> None:
    """Recoverable values clamp to safe bounds and explain each recovery."""
    config = load_config(str(FIXTURES / "invalid-fields.json")).unwrap()
    assert config.lives == 3
    assert config.levels[0].width == 5
    assert config.levels[0].height == 200
    assert isinstance(config.diagnostics, Some)


def test_missing_file_returns_a_diagnostic(tmp_path: Path) -> None:
    """Missing configuration files stay inside the typed error boundary."""
    result = load_config(str(tmp_path / "missing.json"))
    assert isinstance(result, Err)
    assert result.error == ConfigError.NOT_FOUND
    assert isinstance(result.diagnostic, Some)
