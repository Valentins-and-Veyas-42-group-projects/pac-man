PYTHON ?= python3
UV ?= uv
VENV ?= .venv
VENV_PYTHON = $(VENV)/bin/python
MAIN ?= pac-man.py
ARGS ?= config.json
WITH_CPP ?= 0

ifeq ($(WITH_CPP),1)
CPP_TARGET = native
endif

MYPY_FLAGS = --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

FLAKE8 = uv run flake8
MYPY = uv run mypy
PYTEST = uv run pytest
TY = uv run ty

.PHONY: all install run debug clean lint lint-strict test typecheck native native-test native-sanitize native-benchmark prediction-benchmark analysis-benchmark wasm wasm-test package

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

native:
	xmake f -c -m debug --toolchain=clang
	xmake

native-test:
	xmake f -c -m release --toolchain=clang
	xmake build pacman-native-tests
	xmake run pacman-native-tests

native-sanitize:
	xmake f -c -m debug --toolchain=clang -o .build/sanitize --policies=build.sanitizer.address,build.sanitizer.undefined
	xmake build pacman-native-tests pacman-native
	xmake run pacman-native-tests
	xmake f -c -m release --toolchain=clang

native-benchmark:
	xmake f -c -m release --toolchain=clang
	xmake build pacman-native
	uv run python -m delete_me.analyze.pathfinding_benchmark

prediction-benchmark:
	xmake f -c -m release --toolchain=clang
	xmake build pacman-native
	$(VENV_PYTHON) -m delete_me.analyze.prediction_benchmark

analysis-benchmark:
	xmake f -c -p wasm -a wasm32 -m release
	xmake build pacman-wasm
	xmake f -c -m release --toolchain=clang
	xmake build -r pacman-native
	$(VENV_PYTHON) -m delete_me.analyze.analysis_benchmark $(BENCH_ARGS)

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
