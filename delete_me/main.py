# uv run python delete_me/main.py
# Made by Codex as a disposable runner for every feature integration tool.

"""Run every disposable feature integration tool in sequence."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
RUNNERS = (
    ROOT / "config" / "main.py",
    ROOT / "maze" / "main.py",
    ROOT / "replay" / "main.py",
)


def main() -> int:
    """Run all feature tools, stopping after the first failure.

    Returns:
        Zero when every runner succeeds, otherwise the first failure status.
    """
    for runner in RUNNERS:
        print(f"\n== {runner.parent.name} ==", flush=True)
        result = subprocess.run([sys.executable, str(runner)], check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, Exception) as error:
        print(f"test runner failed unexpectedly: {error}")
        raise SystemExit(1) from None
