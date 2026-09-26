"""Run the backend benchmarks and print one compact, comparable report."""

import fcntl
import os
import re
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path


def color(value: str, code: str) -> str:
    """Use restrained terminal color without adding escapes to CI logs.

    Returns:
        Colored text on a terminal, otherwise plain text.
    """
    return f"\033[{code}m{value}\033[0m" if sys.stdout.isatty() and "NO_COLOR" not in os.environ else value


def run(command: list[str], step: int, label: str) -> str | None:
    """Capture normal benchmark chatter; replay it if the command fails.

    Returns:
        Standard output on success, otherwise nothing.
    """
    print(f"{color(f'[{step}/4]', '36')} {label} ... ", end="", flush=True)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        print(color("failed", "31"), flush=True)
        print(f"could not run {' '.join(command)}: {error}", file=sys.stderr)
        return None
    if completed.returncode != 0:
        print(color("failed", "31"), flush=True)
        print(f"failed ({completed.returncode}): {' '.join(command)}", file=sys.stderr)
        print(completed.stdout, end="", file=sys.stderr)
        print(completed.stderr, end="", file=sys.stderr)
        if "not a valid target name for this project" in completed.stdout + completed.stderr:
            print(
                "xmake's mode changed during the build. Stop other xmake jobs, then retry make benchmark.",
                file=sys.stderr,
            )
        return None
    print(color("ok", "32"), flush=True)
    return completed.stdout


def timing(output: str, label: str) -> float | None:
    """Read a benchmark's microseconds without depending on build chatter.

    Returns:
        Measured microseconds, or nothing when the label is absent.
    """
    pattern = rf"(?m)^\s*{re.escape(label)}\s+([\d.]+)\s+us/(?:search|field|call|state|decision|action)"
    match = re.search(pattern, output)
    if match is None:
        # Analysis benchmark prints the unit in the heading, not on each row.
        match = re.search(rf"(?m)^\s*{re.escape(label)}\s+([\d.]+)(?:\s|$)", output)
    return float(match.group(1)) if match else None


def lookup_timing(output: str) -> float | None:
    """Read the direct C++ lookup microbenchmark on its 128-tile ring.

    Returns:
        Microseconds per call, or nothing when that benchmark did not run.
    """
    match = re.search(r"cached distance lookup: ([\d.]+) us/call", output)
    return float(match.group(1)) if match else None


def show_row(name: str, python: float | None, native: float | None, wasm: float | None) -> None:
    """Print measured microseconds and backend speedups against Python."""
    def cell(value: float | None) -> str:
        return f"{value:8.2f}" if value is not None else "       -"

    def ratio(value: float | None) -> str:
        return f"{python / value:6.2f}x" if python is not None and value is not None else "     -"

    print(f"{name:25} {cell(python)} {cell(native)} {cell(wasm)} {ratio(native)} {ratio(wasm)}")


def main() -> int:
    """Verify every available backend and report release and sanitizer timings.

    Returns:
        Zero when every benchmark passes and its timings are readable.
    """
    parser = ArgumentParser()
    parser.add_argument("--seconds", type=int, default=5)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--decision-samples", type=int, default=2)
    parser.add_argument("--decision-rounds", type=int, default=1)
    args = parser.parse_args()
    if min(args.seconds, args.rounds, args.decision_samples, args.decision_rounds) <= 0:
        parser.error("benchmark counts must be positive")
    analysis_args = (
        f"--seconds {args.seconds} --rounds {args.rounds} "
        f"--decision-samples {args.decision_samples} --decision-rounds {args.decision_rounds}"
    )
    commands = (
        ["make", "native-benchmark"],
        ["make", "prediction-benchmark"],
        ["make", "analysis-benchmark", f"BENCH_ARGS={analysis_args}"],
        ["make", "analysis-benchmark-sanitize", f"BENCH_ARGS={analysis_args}"],
    )
    outputs: list[str] = []
    labels = ("Pathfinding: Python, native, WASM", "Ghost prediction: Python, native, WASM",
              "Analysis: Python, native, WASM", "ASan + UBSan: native tests and analysis")
    for step, (command, label) in enumerate(zip(commands, labels, strict=True), 1):
        output = run(command, step, label)
        if output is None:
            return 1
        outputs.append(output)
    bfs, prediction, analysis, sanitized = outputs
    required = (
        (bfs, "Python BFS"), (bfs, "C++ selected cached"), (bfs, "WASM selected cached"),
        (prediction, "Python prediction"), (prediction, "C++ cached prediction"),
        (prediction, "WASM cached prediction"),
        (analysis, "Python reference"), (analysis, "Native C++ via Python"),
        (analysis, "WASM Web Worker"), (analysis, "WASM branch search"),
        (sanitized, "WASM branch search"),
    )
    if any(timing(output, label) is None for output, label in required):
        print("benchmark output changed; could not read all timings", file=sys.stderr)
        for output in outputs:
            print(output, file=sys.stderr)
        return 1

    print("Median time per operation (us; lower is faster). Ratios are Python/backend.")
    print(f"{'Operation':25} {'Python':>8} {'Native':>8} {'WASM':>8} {'Py/N':>6} {'Py/W':>6}")
    python_bfs = timing(bfs, "Python BFS")
    for name, native_label, wasm_label in (
        ("BFS graph one-shot", "C++ graph one-shot", ""),
        ("BFS masked one-shot", "C++ masked one-shot", ""),
        ("BFS graph cached", "C++ graph cached", ""),
        ("BFS masked cached", "C++ masked cached", ""),
        ("BFS selected cached", "C++ selected cached", "WASM selected cached"),
        ("BFS selected batch", "C++ selected batch", ""),
    ):
        show_row(name, python_bfs, timing(bfs, native_label), timing(bfs, wasm_label) if wasm_label else None)
    show_row(
        "Ghost prediction", timing(prediction, "Python prediction"),
        timing(prediction, "C++ cached prediction"), timing(prediction, "WASM cached prediction"),
    )
    # The first pair of analysis rows is prediction plus safe-action evaluation.
    analysis_python = re.findall(r"(?m)^\s*Python reference\s+([\d.]+)", analysis)
    analysis_native = re.findall(r"(?m)^\s*Native C\+\+ via Python\s+([\d.]+)", analysis)
    if len(analysis_python) != 2 or len(analysis_native) != 2:
        print("analysis benchmark did not report both operations", file=sys.stderr)
        return 1
    show_row(
        "Prediction + actions", float(analysis_python[0]), float(analysis_native[0]),
        timing(analysis, "WASM Web Worker"),
    )
    show_row("Full decision", float(analysis_python[1]), float(analysis_native[1]), None)
    show_row("Branch search", None, None, timing(analysis, "WASM branch search"))
    print("\nASan + UBSan (native debug; Python/WASM parity checked again):")
    san_native = re.findall(r"(?m)^\s*Native C\+\+ via Python\s+([\d.]+)", sanitized)
    if len(san_native) != 2:
        print("sanitizer benchmark did not report both native operations", file=sys.stderr)
        return 1
    print(
        f"  prediction + actions {float(san_native[0]):.2f} us/state; "
        f"full decision {float(san_native[1]):.2f} us/decision"
    )
    release_lookup = lookup_timing(bfs)
    sanitizer_lookup = lookup_timing(sanitized)
    if release_lookup is None or sanitizer_lookup is None:
        print("direct C++ cached lookup benchmark did not report a timing", file=sys.stderr)
        return 1
    print(
        f"\nDirect C++ cached lookup, 128-tile ring: "
        f"release {release_lookup:.2f}, sanitized {sanitizer_lookup:.2f} us/call"
    )
    print("\nRun separately:")
    print("  BFS + WASM: make native-benchmark")
    print("  Prediction: make prediction-benchmark")
    print(f"  Analysis:   make analysis-benchmark BENCH_ARGS='{analysis_args}'")
    print(f"  Sanitizers: make analysis-benchmark-sanitize BENCH_ARGS='{analysis_args}'")
    print("  - means that operation has no equivalent benchmark for that backend.")
    return 0


def locked_main() -> int:
    """Keep concurrent benchmark runs from switching xmake modes mid-build.

    Returns:
        The benchmark result, or one if the build lock is unavailable.
    """
    lock_path = Path(".build/benchmark.lock")
    try:
        lock_path.parent.mkdir(exist_ok=True)
        with lock_path.open("a+") as lock_file:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Another benchmark is using xmake; waiting for it to finish...", flush=True)
                fcntl.flock(lock_file, fcntl.LOCK_EX)
            return main()
    except OSError as error:
        print(f"could not lock the benchmark build: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(locked_main())
