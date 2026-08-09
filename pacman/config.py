"""Configuration loading and validation.

Loads the single JSON config file the game is launched with (see
`pac-man.py`), tolerating `#`-style comment lines and clamping any
missing or invalid values to safe defaults instead of crashing, per
the subject's "Faulty config handling" section.
"""

from dataclasses import dataclass
from enum import Enum

from typed_errs import Diagnostic, Err, Result


class ConfigError(Enum):
    """Enumerate failure modes encountered while loading the config
    file."""


def ConfigErr(
    error: ConfigError, diagnostic: Diagnostic | None = None
) -> Err[ConfigError]:
    """Helper to bake module defaults into every config Err."""
    return Err(
        error=error,
        diagnostic=diagnostic,
        namespace="config",
        context_msg="Loading the game configuration failed",
    )


@dataclass
class LevelConfig:
    """Width/height for a single maze level."""


@dataclass
class Config:
    """Game configuration, keys per the subject's suggested list
    (highscore_filename, levels, lives, pacgum, points_per_pacgum,
    points_per_super_pacgum, points_per_ghost, seed,
    level_max_time)."""


def strip_json_comments(raw_text: str) -> str:
    """Strip `#`-prefixed comment lines from a JSON-with-comments file.

    Args:
        raw_text: The raw file contents, possibly containing comment
            lines.

    Returns:
        The text with comment lines removed, ready for `json.loads`.
    """
    raise NotImplementedError


def load_config(path: str) -> Result[Config, ConfigError]:
    """Load and validate the game config from `path`.

    Unknown keys are ignored; missing or invalid values are clamped
    to their defaults with a logged warning rather than raising.

    Args:
        path: Path to the JSON (with comments) config file.

    Returns:
        Ok(Config) on success, Err(ConfigError) on an unrecoverable
        failure (e.g. the file does not exist).
    """
    raise NotImplementedError


def default_config() -> Config:
    """Return a `Config` populated entirely with safe defaults."""
    raise NotImplementedError
