"""Wires config loading, the game engine, and the renderer together."""

import sys

from dataclasses import dataclass

from .cli_fw import Command, arg
from .config import ConfigError, load_config
from .errors import Err, Ok, Result


@dataclass
class MainArgs:
    """CLI schema: a single positional config file path."""

    config_path: str = arg(
        positional=True, help="Path to the JSON (with comments) config file"
    )


def run(args: MainArgs) -> Result[None, ConfigError]:
    """Load the config and run the game loop.

    Args:
        args: Parsed CLI arguments (just the config file path).

    Returns:
        Ok(None) on a clean exit, Err on an unrecoverable failure.
    """
    config_result = load_config(args.config_path)
    match config_result:
        case Err() as err:
            return err
        case Ok():
            raise NotImplementedError
        case _:
            raise AssertionError("unreachable")


def main() -> None:
    """Entry point: `python3 pac-man.py <config.json>`."""
    root = Command(
        name="pac-man",
        short="A Pac-Man recreation",
        schema=MainArgs,
        run=run,
    )
    result = root.execute(sys.argv[1:])
    match result:
        case Ok(_):
            pass
        case Err() as err:
            err.print_diagnostic()
            sys.exit(1)


if __name__ == "__main__":
    main()
