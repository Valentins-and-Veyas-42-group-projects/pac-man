PYTHON ?= python3
UV ?= uv
VENV ?= .venv
VENV_PYTHON = $(VENV)/bin/python
MAIN ?= pac-man.py
ARGS ?= config.json

MYPY_FLAGS = --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

FLAKE8 = uv run flake8
MYPY = uv run mypy
PYTEST = uv run pytest
TY = uv run ty

.PHONY: install run debug clean lint lint-strict test typecheck

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
