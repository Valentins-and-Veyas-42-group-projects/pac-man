PYTHON ?= python3
UV ?= uv
VENV ?= .venv
VENV_PYTHON = $(VENV)/bin/python
MAIN ?= pac-man.py
ARGS ?= config.json
WITH_CPP ?= 0
RELEASE ?= 0
ANALYSIS_PIPELINE_ARGS ?= --case pipeline --width 31 --height 31 --seconds 600 --speed 100 --seed 42 --fumble_rate 0.12
ANALYSIS_SAVED_ARGS ?= --case saved --analysis_limit 5

ifeq ($(WITH_CPP),1)
CPP_TARGET = native
endif

ifeq ($(RELEASE),1)
NATIVE_MODE = release
else
NATIVE_MODE = debug
endif

MYPY_FLAGS = --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

FLAKE8 = uv run flake8
MYPY = uv run mypy
PYTEST = uv run pytest
TY = uv run ty

.PHONY: all install run debug clean lint lint-strict test typecheck native native-test native-sanitize native-benchmark prediction-benchmark analysis-benchmark analysis-benchmark-sanitize analyze wasm wasm-test package compiledb

all: install $(CPP_TARGET)

install:
	uv sync --dev

run:
	uv run python $(MAIN) $(ARGS)

debug:
	uv run python -m pdb $(MAIN) $(ARGS)

clean:
	find . -type d \( -name "__pycache__" -o -name ".mypy_cache" \
		-o -name ".pytest_cache" \) -prune -exec rm -rf {} +
	find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

lint:
	$(FLAKE8) .
	$(MYPY) pacman $(MYPY_FLAGS)

lint-strict:
	$(FLAKE8) .
	$(MYPY) pacman --strict

test:
	$(PYTEST)

typecheck:
	$(TY) check pacman delete_me tests

# Xmake can reuse a sanitized core archive after a mode switch; force the link inputs fresh.
native:
	xmake f -c -m $(NATIVE_MODE) --toolchain=clang
	xmake build -r pacman-native

native-test:
	xmake f -c -m release --toolchain=clang
	xmake build -r pacman-native-tests
	xmake run pacman-native-tests

native-sanitize:
	xmake f -c -m debug --toolchain=clang -o .build/sanitize --policies=build.sanitizer.address,build.sanitizer.undefined
	xmake build -r pacman-native-tests pacman-native pacman-native-benchmark
	xmake run pacman-native-tests
	xmake run pacman-native-benchmark
	xmake f -c -m release --toolchain=clang
	xmake build -r pacman-native

native-benchmark:
	xmake f -c -m release --toolchain=clang
	xmake build -r pacman-native pacman-native-benchmark
	xmake run pacman-native-benchmark
	uv run python -m delete_me.analyze.pathfinding_benchmark

prediction-benchmark:
	xmake f -c -m release --toolchain=clang
	xmake build -r pacman-native
	$(VENV_PYTHON) -m delete_me.analyze.prediction_benchmark

analysis-benchmark:
	xmake f -c -p wasm -a wasm32 -m release
	xmake build pacman-wasm
	xmake f -c -m release --toolchain=clang
	xmake build -r pacman-native
	$(UV) run python -m delete_me.analyze.analysis_benchmark $(BENCH_ARGS)

analysis-benchmark-sanitize:
	$(UV) sync --locked --dev
	xmake f -c -p wasm -a wasm32 -m release
	xmake build pacman-wasm
	xmake f -c -m debug --toolchain=clang -o .build/sanitize --policies=build.sanitizer.address,build.sanitizer.undefined
	xmake build -r pacman-native pacman-native-benchmark
	xmake run pacman-native-benchmark
	@asan_runtime=$$(clang++ -print-file-name=libclang_rt.asan-$$(uname -m).so); \
	test -f "$$asan_runtime" || { echo "Clang ASan runtime unavailable: $$asan_runtime" >&2; exit 1; }; \
	LD_PRELOAD="$$asan_runtime" PACMAN_SANITIZER_PRELOAD=1 ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
	$(VENV_PYTHON) -m delete_me.analyze.analysis_benchmark $(BENCH_ARGS)
	xmake f -c -m release --toolchain=clang
	xmake build -r pacman-native

analyze:
	$(MAKE) native RELEASE=1
	@set -eu; \
	native_library=$$(xmake show -t pacman-native --format=json | $(UV) run python -c 'import json, sys; from pathlib import Path; print(Path(json.load(sys.stdin)["targetfile"]).resolve())'); \
	export PACMAN_NATIVE_LIBRARY="$$native_library" PACMAN_ANALYSIS_BACKEND=native; \
	$(UV) run python -c 'from pacman.analyze.distance_backend import DistanceBackendKind, active_distance_backend; raise SystemExit(0 if active_distance_backend() is DistanceBackendKind.NATIVE else "native library unavailable after build")'; \
	$(UV) run python -m delete_me.analyze.main $(ANALYSIS_PIPELINE_ARGS); \
	$(UV) run python -m delete_me.analyze.main $(ANALYSIS_SAVED_ARGS)

wasm-test:
	xmake f -c -p wasm -a wasm32 -m release
	xmake build pacman-wasm-tests
	xmake run pacman-wasm-tests
	xmake build pacman-wasm
	node web/test-native-engine.mjs
	node web/test-analysis-worker.mjs

wasm:
	xmake f -c -p wasm -a wasm32 -m release
	xmake build pacman-wasm

package:
	$(UV) build --wheel

compiledb:
	xmake project -k compile_commands .build
