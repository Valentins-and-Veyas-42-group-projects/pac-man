"""Configuration loading and validation.

Loads the single JSON config file the game is launched with (see
`pac-man.py`), tolerating `#`-style comment lines and clamping any
missing or invalid values to safe defaults instead of crashing, per
the subject's "Faulty config handling" section.
"""

import json
from dataclasses import dataclass
from enum import Enum, auto
from typing import cast

from python_crimes import DeferStack, closest_string, deferred, pipe
from typed_errs import (
    Diagnostic,
    Err,
    Nothing,
    Ok,
    Option,
    Result,
    Some,
    catch_bubble,
)
from typed_file_io import FileError, open_text

NO_DIAGNOSTIC: Option[Diagnostic] = Nothing()
NO_LIMIT: Option[int] = Nothing()
MISSING = object()
CONFIG_KEYS = (
    "highscore_filename",
    "levels",
    "lives",
    "pacgum",
    "points_per_pacgum",
    "points_per_super_pacgum",
    "points_per_ghost",
    "seed",
    "level_max_time",
)
LEVEL_KEYS = ("width", "height", "seed", "time")


class ConfigError(Enum):
    """Enumerate unrecoverable failures encountered while loading config."""

    NOT_FOUND = auto()
    UNREADABLE = auto()
    INVALID_JSON = auto()
    INVALID_ROOT = auto()


def ConfigErr(
    error: ConfigError,
    diagnostic: Option[Diagnostic] = NO_DIAGNOSTIC,
) -> Err[ConfigError]:
    """Create a configuration error with shared diagnostic metadata.

    Args:
        error: Configuration error variant.
        diagnostic: Optional source diagnostic describing the failure.

    Returns:
        A typed configuration Err with the module namespace and context.
    """
    return Err(
        error=error,
        diagnostic=diagnostic,
        namespace="config",
        context_msg="Loading the game configuration failed",
    )


@dataclass
class LevelConfig:
    """Configuration values for a single maze level.

    Attributes:
        width: Maze width.
        height: Maze height.
        seed: Optional deterministic maze-generation seed.
        time: Maximum level duration in seconds.
    """

    width: int
    height: int
    seed: Option[int]
    time: int


@dataclass
class Config:
    """Validated game configuration.

    Attributes:
        highscore_filename: Path used for persistent highscores.
        lives: Number of starting lives.
        pacgum: Number of normal pacgums generated for a level.
        points_per_pacgum: Score awarded for a normal pacgum.
        points_per_super_pacgum: Score awarded for a super pacgum.
        points_per_ghost: Score awarded for eating a ghost.
        levels: Maze configuration for each level.
        diagnostics: Recovery information for missing or invalid fields.
    """

    highscore_filename: str
    lives: int
    pacgum: int
    points_per_pacgum: int
    points_per_super_pacgum: int
    points_per_ghost: int
    levels: list[LevelConfig]
    diagnostics: Option[list[Diagnostic]]


def strip_json_comments(raw_text: str) -> str:
    """Strip full-line `#` comments while preserving source line numbers.

    A line is considered a comment when its first non-whitespace
    character is `#`. Comment lines are replaced with empty lines rather
    than removed so JSON parser diagnostics still refer to the original
    source line numbers.

    Args:
        raw_text: Raw configuration file contents.

    Returns:
        JSON-compatible text with comment lines replaced by blank lines.
    """
    return "\n".join(
        "" if line.lstrip().startswith("#") else line
        for line in raw_text.splitlines()
    )


def _first_token_span(line: str) -> tuple[int, int]:
    """Return the source span of the first non-whitespace character.

    Args:
        line: Source line to inspect.

    Returns:
        A zero-based half-open column span suitable for Diagnostic.
    """
    for index, character in enumerate(line):
        if not character.isspace():
            return index, index + 1

    return 0, 1


def _first_nonempty_line(text: str) -> tuple[int, str]:
    """Find the first non-empty source line.

    Args:
        text: Source text to inspect.

    Returns:
        A tuple containing the one-based line number and source text.
    """
    for line_num, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            return line_num, line

    return 1, ""


def _recovery_diagnostic(
    key: str,
    filename: str,
    help_msg: str,
) -> Diagnostic:
    """Build a retrievable diagnostic for a recovered field.

    Returns:
        A diagnostic containing the recovery message.
    """
    return Diagnostic(
        filename=filename,
        line_num=1,
        line_text=key,
        col_start=0,
        col_end=max(1, len(key)),
        help_msg=Some(help_msg),
    )


def _recovery_diagnostics(
    data: dict[str, object],
    filename: str,
) -> list[Diagnostic]:
    """Describe every field normalization and ignored unknown key.

    Returns:
        Structured diagnostics that callers may render or ignore.
    """
    diagnostics: list[Diagnostic] = []

    for key in data.keys() - set(CONFIG_KEYS):
        suggestion = closest_string(key, CONFIG_KEYS)
        message = f"Unknown key {key!r} was ignored."
        if isinstance(suggestion, Some) and suggestion.value.distance <= 3:
            message += f" Did you mean {suggestion.value.value!r}?"
        diagnostics.append(_recovery_diagnostic(key, filename, message))

    expected_types: dict[str, type[object]] = {
        "highscore_filename": str,
        "levels": list,
        "lives": int,
        "pacgum": int,
        "points_per_pacgum": int,
        "points_per_super_pacgum": int,
        "points_per_ghost": int,
        "seed": int,
        "level_max_time": int,
    }
    for key, expected in expected_types.items():
        value = data.get(key, MISSING)
        invalid = value is MISSING or not isinstance(value, expected)
        if expected is int and isinstance(value, bool):
            invalid = True
        if key == "highscore_filename" and value == "":
            invalid = True
        if key == "levels" and value == []:
            invalid = True
        if invalid:
            reason = "missing" if value is MISSING else "invalid"
            diagnostics.append(
                _recovery_diagnostic(
                    key,
                    filename,
                    f"Config key {key!r} is {reason}; using its safe default.",
                )
            )

    integer_ranges = {
        "lives": (1, 99),
        "pacgum": (1, 1_000_000),
        "points_per_pacgum": (0, 1_000_000),
        "points_per_super_pacgum": (0, 1_000_000),
        "points_per_ghost": (0, 1_000_000),
        "level_max_time": (1, 3600),
    }
    for key, (minimum, maximum) in integer_ranges.items():
        value = data.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            if value < minimum or value > maximum:
                diagnostics.append(
                    _recovery_diagnostic(
                        key,
                        filename,
                        f"Config key {key!r} was clamped to {minimum}..{maximum}.",
                    )
                )

    levels = data.get("levels")
    if isinstance(levels, list):
        for index, raw_level in enumerate(cast(list[object], levels)):
            if not isinstance(raw_level, dict):
                diagnostics.append(
                    _recovery_diagnostic(
                        f"levels[{index}]",
                        filename,
                        f"Level {index} is invalid; using its safe default.",
                    )
                )
                continue
            level = cast(dict[object, object], raw_level)
            for raw_key in level:
                if isinstance(raw_key, str) and raw_key not in LEVEL_KEYS:
                    suggestion = closest_string(raw_key, LEVEL_KEYS)
                    message = f"Unknown level key {raw_key!r} was ignored."
                    if (
                        isinstance(suggestion, Some)
                        and suggestion.value.distance <= 3
                    ):
                        message += f" Did you mean {suggestion.value.value!r}?"
                    diagnostics.append(
                        _recovery_diagnostic(raw_key, filename, message)
                    )
            for key in ("width", "height"):
                value = level.get(key, MISSING)
                if not isinstance(value, int) or isinstance(value, bool):
                    diagnostics.append(
                        _recovery_diagnostic(
                            f"levels[{index}].{key}",
                            filename,
                            f"Level {index} key {key!r} is missing or invalid; using its default.",
                        )
                    )
                elif value < 5 or value > 200:
                    diagnostics.append(
                        _recovery_diagnostic(
                            f"levels[{index}].{key}",
                            filename,
                            f"Level {index} key {key!r} was clamped to 5..200.",
                        )
                    )

    return diagnostics


@pipe
def config_file_error(error: Err[FileError]) -> Err[ConfigError]:
    """Convert a file-layer error into the configuration error domain.

    The underlying file diagnostic is preserved so paths and source
    locations remain available to the existing diagnostic printer.

    Args:
        error: File error returned by typed-file-io.

    Returns:
        A configuration error containing the original file diagnostic.
    """
    kind = (
        ConfigError.NOT_FOUND
        if error.error is FileError.FILE_NOT_FOUND
        else ConfigError.UNREADABLE
    )
    help_msg = (
        "Check that the configuration path exists and is readable."
        if kind is ConfigError.NOT_FOUND
        else "Check the configuration path and file permissions."
    )
    if isinstance(error.diagnostic, Some):
        source = error.diagnostic.value
        diagnostic: Option[Diagnostic] = Some(
            Diagnostic(
                filename=source.filename,
                line_num=source.line_num,
                line_text=source.line_text,
                col_start=source.col_start,
                col_end=source.col_end,
                help_msg=Some(help_msg),
            )
        )
    else:
        diagnostic = Nothing()
    return ConfigErr(kind, diagnostic)


@pipe
def parse_json(
    raw_text: str,
    *,
    filename: str,
) -> Result[dict[str, object], ConfigError]:
    """Parse configuration JSON with precise source diagnostics.

    Args:
        raw_text: JSON text after full-line comments were stripped.
        filename: Source filename displayed in diagnostics.

    Returns:
        Ok containing the top-level JSON object, or Err when the JSON is
        malformed or the top-level value is not an object.
    """
    try:
        value = cast(object, json.loads(raw_text))
    except json.JSONDecodeError as error:
        lines = raw_text.splitlines()

        line_text = (
            lines[error.lineno - 1] if 1 <= error.lineno <= len(lines) else ""
        )

        col_start = max(0, error.colno - 1)

        return ConfigErr(
            ConfigError.INVALID_JSON,
            Some(
                Diagnostic(
                    filename=filename,
                    line_num=error.lineno,
                    line_text=line_text,
                    col_start=col_start,
                    col_end=col_start + 1,
                    help_msg=Some(error.msg),
                )
            ),
        )

    if not isinstance(value, dict):
        line_num, line_text = _first_nonempty_line(raw_text)
        col_start, col_end = _first_token_span(line_text)

        return ConfigErr(
            ConfigError.INVALID_ROOT,
            Some(
                Diagnostic(
                    filename=filename,
                    line_num=line_num,
                    line_text=line_text,
                    col_start=col_start,
                    col_end=col_end,
                    help_msg=(
                        Some(
                            "Expected the top-level configuration value to be a JSON object."
                        )
                    ),
                )
            ),
        )

    data: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            return ConfigErr(ConfigError.INVALID_ROOT)
        data[key] = item

    return Ok(data)


def _int_field(
    data: dict[str, object],
    key: str,
    default: int,
    *,
    minimum: Option[int] = NO_LIMIT,
    maximum: Option[int] = NO_LIMIT,
) -> int:
    """Read and clamp an integer configuration field.

    Missing values, booleans, and non-integer values fall back to the
    supplied default. Valid integers outside the safe range are clamped.

    Args:
        data: JSON object containing the field.
        key: Field name.
        default: Value used when the field is missing or invalid.
        minimum: Optional inclusive minimum.
        maximum: Optional inclusive maximum.

    Returns:
        A validated integer value.
    """
    value = data.get(key, MISSING)

    if not isinstance(value, int) or isinstance(value, bool):
        return default

    if isinstance(minimum, Some):
        value = max(minimum.value, value)

    if isinstance(maximum, Some):
        value = min(maximum.value, value)

    return value


def _str_field(
    data: dict[str, object],
    key: str,
    default: str,
) -> str:
    """Read a non-empty string configuration field.

    Args:
        data: JSON object containing the field.
        key: Field name.
        default: Value used when the field is missing or invalid.

    Returns:
        A validated string value.
    """
    value = data.get(key, MISSING)

    if not isinstance(value, str) or not value:
        return default

    return value


def _seed_field(
    value: object,
    default: Option[int],
) -> Option[int]:
    """Validate an optional deterministic level seed.

    Args:
        value: Raw JSON seed value.
        default: Default seed used for invalid input.

    Returns:
        Some containing a valid integer seed, Nothing for an explicit
        null value, or the supplied default for invalid values.
    """
    if value is MISSING:
        return default

    if value is None:
        return Nothing()

    if isinstance(value, int) and not isinstance(value, bool):
        return Some(value)

    return default


def _level_from_json(
    value: object,
    default: LevelConfig,
) -> LevelConfig:
    """Validate one level configuration object.

    Args:
        value: Raw JSON value representing a level.
        default: Level defaults used for missing or invalid fields.

    Returns:
        A fully validated LevelConfig.
    """
    if not isinstance(value, dict):
        return default

    data: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            return default
        data[key] = item

    return LevelConfig(
        width=_int_field(
            data,
            "width",
            default.width,
            minimum=Some(5),
            maximum=Some(200),
        ),
        height=_int_field(
            data,
            "height",
            default.height,
            minimum=Some(5),
            maximum=Some(200),
        ),
        seed=_seed_field(
            data.get("seed", MISSING),
            default.seed,
        ),
        time=_int_field(
            data,
            "time",
            default.time,
            minimum=Some(1),
            maximum=Some(3600),
        ),
    )


def _levels_field(
    data: dict[str, object],
    defaults: list[LevelConfig],
) -> list[LevelConfig]:
    """Validate the configured maze level list.

    Args:
        data: Top-level configuration object.
        defaults: Default level configurations.

    Returns:
        A validated non-empty list of levels.
    """
    value = data.get("levels")

    if not isinstance(value, list) or not value:
        return defaults

    levels: list[LevelConfig] = []

    for index, raw_level in enumerate(cast(list[object], value)):
        default = defaults[min(index, len(defaults) - 1)]
        levels.append(_level_from_json(raw_level, default))

    return levels


@pipe
def validate_config(
    data: dict[str, object],
    *,
    filename: str = "<config>",
) -> Config:
    """Normalize configuration fields into safe domain values.

    Invalid or missing individual fields are recoverable and therefore
    replaced with defaults or clamped to safe bounds rather than
    returning an Err.

    Args:
        data: Parsed top-level configuration object.
        filename: Configuration source used in recovery diagnostics.

    Returns:
        A fully validated Config.
    """
    defaults = default_config()
    diagnostics = _recovery_diagnostics(data, filename)
    level_time = _int_field(
        data,
        "level_max_time",
        defaults.levels[0].time,
        minimum=Some(1),
        maximum=Some(3600),
    )
    first_seed = _seed_field(
        data.get("seed", MISSING), defaults.levels[0].seed
    )
    level_defaults = [
        LevelConfig(
            width=level.width,
            height=level.height,
            seed=first_seed if index == 0 else level.seed,
            time=level_time,
        )
        for index, level in enumerate(defaults.levels)
    ]

    return Config(
        highscore_filename=_str_field(
            data,
            "highscore_filename",
            defaults.highscore_filename,
        ),
        lives=_int_field(
            data,
            "lives",
            defaults.lives,
            minimum=Some(1),
            maximum=Some(99),
        ),
        pacgum=_int_field(
            data,
            "pacgum",
            defaults.pacgum,
            minimum=Some(1),
            maximum=Some(1_000_000),
        ),
        points_per_pacgum=_int_field(
            data,
            "points_per_pacgum",
            defaults.points_per_pacgum,
            minimum=Some(0),
            maximum=Some(1_000_000),
        ),
        points_per_super_pacgum=_int_field(
            data,
            "points_per_super_pacgum",
            defaults.points_per_super_pacgum,
            minimum=Some(0),
            maximum=Some(1_000_000),
        ),
        points_per_ghost=_int_field(
            data,
            "points_per_ghost",
            defaults.points_per_ghost,
            minimum=Some(0),
            maximum=Some(1_000_000),
        ),
        levels=_levels_field(
            data,
            level_defaults,
        ),
        diagnostics=Some(diagnostics) if diagnostics else Nothing(),
    )


@catch_bubble
@deferred
def load_config(
    defer: DeferStack,
    path: str,
) -> Result[Config, ConfigError]:
    """Load and validate the game configuration from a file.

    The file is explicitly closed through the deferred cleanup stack.
    File errors are translated into the configuration error domain while
    preserving their diagnostics. JSON comments are stripped before
    parsing, and recoverable field errors are normalized to safe values.

    Args:
        defer: Function-scoped deferred cleanup stack.
        path: Path to the JSON configuration file.

    Returns:
        Ok containing a validated Config, or Err for an unrecoverable
        file, JSON syntax, or top-level structure failure.
    """
    reader = open_text(path).map_err_with(config_file_error).q

    defer << reader.close

    return (
        reader.read()
        .map_err_with(config_file_error)
        .map(strip_json_comments)
        .and_then(parse_json.with_(filename=path))
        .map(validate_config.with_(filename=path))
    )


def default_config() -> Config:
    """Return a Config populated entirely with safe defaults.

    Returns:
        A default configuration containing at least ten playable levels.
    """
    return Config(
        highscore_filename="highscores.db",
        lives=3,
        pacgum=42,
        points_per_pacgum=10,
        points_per_super_pacgum=50,
        points_per_ghost=200,
        levels=[
            LevelConfig(
                width=21,
                height=21,
                seed=Some(index),
                time=120,
            )
            for index in range(10)
        ],
        diagnostics=Nothing(),
    )
