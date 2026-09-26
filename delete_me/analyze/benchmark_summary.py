"""Run the backend benchmarks and print one compact, comparable report."""

import fcntl
import os
import re
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path
from time import perf_counter


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
    started = perf_counter()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        print(f"{color('failed', '31')}  {perf_counter() - started:.1f}s", flush=True)
        print(f"could not run {' '.join(command)}: {error}", file=sys.stderr)
        return None
    if completed.returncode != 0:
        print(f"{color('failed', '31')}  {perf_counter() - started:.1f}s", flush=True)
        print(f"failed ({completed.returncode}): {' '.join(command)}", file=sys.stderr)
        print(completed.stdout, end="", file=sys.stderr)
        print(completed.stderr, end="", file=sys.stderr)
        if "not a valid target name for this project" in completed.stdout + completed.stderr:
            print(
                "xmake's mode changed during the build. Stop other xmake jobs, then retry make benchmark.",
                file=sys.stderr,
            )
        return None
    print(f"{color('ok', '32')}  {perf_counter() - started:.1f}s", flush=True)
    return completed.stdout


def timing(output: str, label: str) -> float | None:
    """Read a benchmark's microseconds without depending on build chatter.

    Returns:
        Measured microseconds, or nothing when the label is absent.
    """
    pattern = rf"(?m)^\s*{re.escape(label)}\s+([\d.]+)\s+us/(?:search|field|call|state|decision|action|graph)"
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
        return f"{value:.2f} µs" if value is not None else "-"

    def ratio(value: float | None) -> str:
        return f"{python / value:.2f}×" if python is not None and value is not None else "-"

    print(table_row(name, cell(python), cell(native), cell(wasm), ratio(native), ratio(wasm)))


def table_row(name: str, python: str, native: str, wasm: str, native_ratio: str, wasm_ratio: str) -> str:
    """Keep labels, units, and ratios in the same fixed columns.

    Returns:
        One terminal-width table row.
    """
    return (
        f" {name:<20} │ {python:>11} │ {native:>11} │ {wasm:>11} "
        f"│ {native_ratio:>7} │ {wasm_ratio:>7}"
    )


def table_rule() -> str:
    """Separate header and data without dangling column junctions.

    Returns:
        A separator spanning every column.
    """
    return " " + "─" * 82


def table_header(title: str) -> None:
    """Start one complete table so columns do not straddle section labels."""
    print(f"\n{color(title, '36')}")
    print(table_row("Operation", "Python", "C++/Py", "WASM/JS", "C++×", "WASM×"))
    print(color(table_rule(), "2"))


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
    started = perf_counter()
    outputs: list[str] = []
    labels = ("Pathfinding: Python, native, WASM", "Ghost prediction: Python, native, WASM",
              "Analysis: Python, native, WASM", "ASan + UBSan: native tests and analysis")
    for step, (command, label) in enumerate(zip(commands, labels, strict=True), 1):
        output = run(command, step, label)
        if output is None:
            return 1
        outputs.append(output)
    bfs, prediction, analysis, sanitized = outputs
    bfs_modes = (
        ("Graph, one shot", "graph one-shot"),
        ("Masked, one shot", "masked one-shot"),
        ("Graph, cached", "graph cached"),
        ("Masked, cached", "masked cached"),
        ("Selected, cached", "selected cached"),
        ("Selected, batch", "selected batch"),
    )
    required = (
        (bfs, "Python BFS"),
        *((bfs, f"{prefix} {mode}") for _, mode in bfs_modes for prefix in ("C++", "WASM")),
        (bfs, "C++ ABI cached lookup"), (bfs, "C++ Python result decode"),
        (bfs, "C++ Python graph encode"),
        (prediction, "Python prediction"), (prediction, "C++ cached prediction"),
        (prediction, "WASM cached prediction"), (prediction, "C++ ABI prediction"),
        (prediction, "C++ Python result decode"),
        (analysis, "Python reference"), (analysis, "Native C++ via Python"),
        (analysis, "WASM Web Worker"), (analysis, "WASM branch search"),
        (analysis, "Python branch"), (analysis, "Native branch"),
        (sanitized, "WASM branch search"),
    )
    if any(timing(output, label) is None for output, label in required):
        print("benchmark output changed; could not read all timings", file=sys.stderr)
        for output in outputs:
            print(output, file=sys.stderr)
        return 1

    print(f"\n{color('Backend speeds', '1')}  median µs per operation; lower is faster")
    print("  C++/Py includes Python conversion; WASM/JS includes JS conversion.")
    print("  Safety and branch WASM calls include worker IPC; × is speedup vs Python.")
    table_header("Pathfinding (per distance field)")
    python_bfs = timing(bfs, "Python BFS")
    for name, mode in bfs_modes:
        show_row(name, python_bfs, timing(bfs, f"C++ {mode}"), timing(bfs, f"WASM {mode}"))
    table_header("Analysis (prediction, state, or action per row)")
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
    show_row(
        "Branch search", timing(analysis, "Python branch"),
        timing(analysis, "Native branch"), timing(analysis, "WASM branch search"),
    )
    print("  One-shot C++/Py re-encodes the graph per call; WASM/JS gets flat bytes.")

    abi_bfs = timing(bfs, "C++ ABI cached lookup")
    decode_bfs = timing(bfs, "C++ Python result decode")
    wrapped_bfs = timing(bfs, "C++ selected cached")
    wasm_bfs = timing(bfs, "WASM selected cached")
    abi_prediction = timing(prediction, "C++ ABI prediction")
    decode_prediction = timing(prediction, "C++ Python result decode")
    wrapped_prediction = timing(prediction, "C++ cached prediction")
    wasm_prediction = timing(prediction, "WASM cached prediction")
    graph_encoding = timing(bfs, "C++ Python graph encode")
    graph_total = timing(bfs, "C++ graph one-shot")
    graph_wasm = timing(bfs, "WASM graph one-shot")
    if (
        abi_bfs is None or decode_bfs is None or wrapped_bfs is None or wasm_bfs is None
        or abi_prediction is None or decode_prediction is None
        or wrapped_prediction is None or wasm_prediction is None
        or graph_encoding is None or graph_total is None or graph_wasm is None
    ):
        print("native ABI breakdown is incomplete", file=sys.stderr)
        return 1
    print("\nNative ctypes breakdown (same maze, µs/call)")
    print(
        f"  {'Operation':20} {'ABI':>7} {'Decode':>8} {'Other Py':>8} "
        f"{'C++/Py':>8} {'WASM/JS':>8} {'Δ':>8}"
    )
    print("  " + "─" * 77)
    for name, abi, decode, wrapped, wasm in (
        ("Cached BFS", abi_bfs, decode_bfs, wrapped_bfs, wasm_bfs),
        ("Ghost prediction", abi_prediction, decode_prediction, wrapped_prediction, wasm_prediction),
    ):
        print(
            f"  {name:20} {abi:7.2f} {decode:8.2f} {wrapped - abi - decode:8.2f} "
            f"{wrapped:8.2f} {wasm:8.2f} {wrapped - wasm:+8.2f}"
        )
    print("  Other Py = total − ABI − decode; Δ = C++/Py − WASM/JS.")
    print(f"  Graph one-shot encoding: {graph_encoding:.2f} µs/graph")
    print(
        f"  Graph one-shot totals: C++/Py {graph_total:.2f} µs, "
        f"WASM/JS {graph_wasm:.2f} µs, Δ {graph_total - graph_wasm:+.2f} µs"
    )
    print("\nFull decision through Python")
    print(f"  {'Python':20} {float(analysis_python[1]):.2f} µs/decision")
    print(
        f"  {'Native-backed':20} {float(analysis_native[1]):.2f} µs/decision"
        f"  ({float(analysis_python[1]) / float(analysis_native[1]):.2f}×)"
    )
    print("  The WASM worker exposes the measured kernels above, not a full decision call.")

    print("\nASan + UBSan (native debug; parity checked again)")
    san_native = re.findall(r"(?m)^\s*Native C\+\+ via Python\s+([\d.]+)", sanitized)
    if len(san_native) != 2:
        print("sanitizer benchmark did not report both native operations", file=sys.stderr)
        return 1
    print(f"  {'Prediction + actions':20} {float(san_native[0]):.2f} µs/state")
    print(f"  {'Full decision':20} {float(san_native[1]):.2f} µs/decision")
    release_lookup = lookup_timing(bfs)
    sanitizer_lookup = lookup_timing(sanitized)
    if release_lookup is None or sanitizer_lookup is None:
        print("direct C++ cached lookup benchmark did not report a timing", file=sys.stderr)
        return 1
    print("\nC++ cached lookup, 128-tile ring")
    print(f"  {'Release':20} {release_lookup:.2f} µs/call")
    print(f"  {'Sanitized':20} {sanitizer_lookup:.2f} µs/call")

    print("\nRun separately")
    print("  make native-benchmark")
    print("  make prediction-benchmark")
    print("  make analysis-benchmark")
    print("  make analysis-benchmark-sanitize")
    print(f"\nTotal benchmark time: {perf_counter() - started:.1f}s")
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
