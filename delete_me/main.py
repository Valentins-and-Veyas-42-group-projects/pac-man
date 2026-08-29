# uv run python delete_me/main.py
# Made by Codex as a disposable runner for every feature integration tool.

"""Run every disposable feature integration tool in sequence."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
RUNNERS: tuple[tuple[str, ...], ...] = (
    (str(ROOT / "config" / "main.py"),),
    (str(ROOT / "highscores" / "main.py"),),
    (str(ROOT / "maze" / "main.py"),),
    (str(ROOT / "replay" / "main.py"),),
    ("-m", "delete_me.analyze.main"),
)


def main() -> int:
    """Run all feature tools, stopping after the first failure.

    Returns:
        Zero when every runner succeeds, otherwise the first failure status.
    """
    for runner in RUNNERS:
        name = "analyze" if runner[0] == "-m" else Path(runner[0]).parent.name
        print(f"\n== {name} ==", flush=True)
        result = subprocess.run([sys.executable, *runner], check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, Exception) as error:
        print(f"test runner failed unexpectedly: {error}")
        raise SystemExit(1) from None
