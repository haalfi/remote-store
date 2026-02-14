.PHONY: help install lint format typecheck test test-cov examples all clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install package with dev dependencies
	pip install -e ".[dev]"

lint: ## Run ruff linter
	ruff check src/ tests/ examples/

format: ## Run ruff formatter (fix in place)
	ruff format src/ tests/ examples/

format-check: ## Check formatting without modifying files
	ruff format --check src/ tests/ examples/

typecheck: ## Run mypy strict type checking
	mypy src/

test: ## Run tests
	pytest

test-cov: ## Run tests with coverage report (fail under 95%)
	pytest --cov=remote_store --cov-report=term-missing --cov-fail-under=95

examples: ## Run all example scripts
	python examples/quickstart.py
	python examples/file_operations.py
	python examples/streaming_io.py
	python examples/atomic_writes.py
	python examples/configuration.py
	python examples/error_handling.py

all: lint format-check typecheck test-cov examples ## Run all checks

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
