# uv run python delete_me/config/main.py
# Made by Codex as a disposable configuration integration runner.

"""Exercise the config parser against the development fixtures."""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from cli_fw import Command, arg
from pacman.config import Config, load_config
from typed_errs import Err, Some

FIXTURE_DIR = Path(__file__).parent / "fixtures"
EXPECTED_REJECTIONS = {
    "invalid-root.json",
    "malformed-json.json",
}
GREEN = "\033[1;32m"
RED = "\033[1;31m"
CYAN = "\033[1;36m"
RESET = "\033[0m"


@dataclass
class ConfigTestArgs:
    """Arguments accepted by the configuration test tool."""

    files: list[Path] = cast(
        list[Path],
        arg(
            positional=True,
            default_factory=list,
            help="Config files to load; defaults to every bundled fixture",
        ),
    )


def _print_config(config: Config) -> None:
    """Print the important normalized configuration values."""
    print(f"    highscore: {config.highscore_filename}")
    print(f"    lives: {config.lives}  pacgums: {config.pacgum}")
    points = (
        f"pacgum={config.points_per_pacgum}",
        f"super={config.points_per_super_pacgum}",
        f"ghost={config.points_per_ghost}",
    )
    print(f"    points: {' '.join(points)}")
    print(f"    levels: {len(config.levels)}")
    if isinstance(config.diagnostics, Some):
        print(f"    recovered: {len(config.diagnostics.value)} issue(s)")
        for diagnostic in config.diagnostics.value:
            if isinstance(diagnostic.help_msg, Some):
                print(f"      ! {diagnostic.help_msg.value}")


def run(args: ConfigTestArgs) -> int:
    """Load selected fixtures and print a compact result summary.

    Args:
        args: Parsed fixture paths.

    Returns:
        Zero when every fixture behaves as expected, otherwise one.
    """
    paths = args.files or sorted(FIXTURE_DIR.glob("*.json"))
    failures = 0

    print(f"{CYAN}Config parser fixtures{RESET} ({len(paths)})\n")
    for path in paths:
        expected_rejection = not args.files and path.name in EXPECTED_REJECTIONS
        result = load_config(str(path))

        if isinstance(result, Err):
            if expected_rejection:
                print(f"{GREEN}✓{RESET} {path.name}: rejected as expected")
            else:
                failures += 1
                print(f"{RED}✗{RESET} {path}: rejected")
            result.print_diagnostic()
            print()
            continue

        if expected_rejection:
            failures += 1
            print(f"{RED}✗{RESET} {path.name}: unexpectedly loaded")
        else:
            print(f"{GREEN}✓{RESET} {path.name}: loaded")
        _print_config(result.value)
        print()

    passed = len(paths) - failures
    color = GREEN if failures == 0 else RED
    print(f"{color}{passed}/{len(paths)} fixtures behaved as expected{RESET}")
    return int(failures != 0)


def main() -> None:
    """Parse CLI arguments and run the fixture loader.

    Raises:
        SystemExit: With the CLI or fixture result status.
    """
    command = Command(
        name="config-test",
        short="Exercise Pac-Man configuration loading",
        long="Load bundled fixtures or explicit config files through pacman.config",
        example="uv run python delete_me/config/main.py config.example.json",
        schema=ConfigTestArgs,
        run=run,
    )
    result = command.execute(sys.argv[1:])
    if isinstance(result, Err):
        result.print_diagnostic()
        raise SystemExit(2)
    raise SystemExit(cast(int, result.value))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, Exception) as error:
        print(f"config-test failed unexpectedly: {error}")
        raise SystemExit(1) from None
