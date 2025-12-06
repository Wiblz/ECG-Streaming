.PHONY: fmt check vet test lint install clean help

# Activate venv and run commands
VENV := .venv/bin/activate
RUN := . $(VENV) &&

# Format code
fmt:
	@echo "Formatting code with ruff..."
	$(RUN) ruff format src/
	@echo "✓ Code formatted"

# Check formatting without modifying
fmt-check:
	@echo "Checking formatting..."
	$(RUN) ruff format --check --diff src/

# Type checking
vet:
	@echo "Running type checks with mypy..."
	$(RUN) mypy src/
	@echo "✓ Type checking complete"

# Linting
lint:
	@echo "Running linter with ruff..."
	$(RUN) ruff check src/
	@echo "✓ Linting complete"

# Lint and auto-fix
lint-fix:
	@echo "Running linter with auto-fix..."
	$(RUN) ruff check --fix src/

# Run all checks (format + lint + type check)
check: fmt lint vet
	@echo "✓ All checks passed"

# Quick check without formatting
check-only: lint vet
	@echo "✓ All checks passed"

# Run tests
test:
	@echo "Running tests..."
	$(RUN) pytest -v

# Install dependencies
install:
	@echo "Installing dependencies..."
	$(RUN) uv pip install -e ".[dev]"

# Install without dev dependencies
install-prod:
	@echo "Installing production dependencies..."
	$(RUN) uv pip install -e .

# Clean up generated files
clean:
	@echo "Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleaned up"

# Show help
help:
	@echo "ECG Streaming - Development Commands"
	@echo ""
	@echo "Formatting:"
	@echo "  make fmt         Format code with ruff"
	@echo "  make fmt-check   Check formatting without making changes"
	@echo ""
	@echo "Type Checking:"
	@echo "  make vet         Run mypy type checker"
	@echo ""
	@echo "Linting:"
	@echo "  make lint        Run ruff linter"
	@echo "  make lint-fix    Run ruff linter with auto-fix"
	@echo ""
	@echo "Combined:"
	@echo "  make check       Run fmt + lint + vet (recommended before commit)"
	@echo "  make check-only  Run lint + vet without formatting"
	@echo ""
	@echo "Testing:"
	@echo "  make test        Run pytest tests"
	@echo ""
	@echo "Setup:"
	@echo "  make install     Install all dependencies including dev tools"
	@echo "  make install-prod Install only production dependencies"
	@echo "  make clean       Remove generated files and caches"
