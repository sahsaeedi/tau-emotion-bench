# Run tools from the active virtual environment, or through uv when none is active.
RUN := $(if $(VIRTUAL_ENV),,uv run )

# Default target
.PHONY: all
all: help

## Clean up generated files and virtual environment
.PHONY: clean
clean:
	rm -rf .venv
	rm -rf __pycache__
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf dist
	rm -rf build

## Run core tests (requires: uv sync --extra dev)
.PHONY: test
test:
	$(RUN)pytest tests/

## Run all tests (requires: uv sync --all-extras)
.PHONY: test-all
test-all:
	$(RUN)pytest tests/

## Start the Environment CLI for interacting with domain environments
.PHONY: env-cli
env-cli:
	$(RUN)python -m tau_emotion.environment.utils.interface_agent

## Lint code with ruff
.PHONY: lint
lint:
	$(RUN)ruff check .

## Format code with ruff
.PHONY: format
format:
	$(RUN)ruff format .

## Lint and fix issues automatically
.PHONY: lint-fix
lint-fix:
	$(RUN)ruff check --fix .

## Run both linting and formatting
.PHONY: check-all
check-all: lint format

## Install pre-commit hooks
.PHONY: setup-hooks
setup-hooks:
	$(RUN)pre-commit install

## Display online help for commonly used targets in this Makefile
.PHONY: help
help:
	@awk '/^[a-zA-Z_\/\.0-9-]+:/ {        \
		nb = sub( /^## /, "", helpMsg );  \
		if (nb)                           \
			print  $$1 "\t" helpMsg;      \
	}                                     \
	{ helpMsg = $$0 }' $(MAKEFILE_LIST) | \
	column -ts $$'\t' |                   \
	expand -t 1 |                         \
	grep --color '^[^ ]*'
