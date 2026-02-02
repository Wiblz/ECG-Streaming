# ECG Streaming - Main Makefile
# Python development and build commands

.PHONY: fmt check vet test lint install clean proto help

# Activate venv and run commands
VENV := .venv/bin/activate
RUN := . $(VENV) &&

# Package directories
PACKAGES := packages/ecg-common packages/ecg-collector packages/ecg-aggregator

# ============================================================================
# Code Quality
# ============================================================================

# Format code
fmt:
	@echo "Formatting code with ruff..."
	$(RUN) ruff format $(PACKAGES)
	@echo "✓ Code formatted"

# Check formatting without modifying
fmt-check:
	@echo "Checking formatting..."
	$(RUN) ruff format --check --diff $(PACKAGES)

# Type checking
vet:
	@echo "Running type checks with mypy..."
	$(RUN) mypy $(PACKAGES)
	@echo "✓ Type checking complete"

# Linting
lint:
	@echo "Running linter with ruff..."
	$(RUN) ruff check $(PACKAGES) --exclude "*_pb2*.py"
	@echo "✓ Linting complete"

# Lint and auto-fix
lint-fix:
	@echo "Running linter with auto-fix..."
	$(RUN) ruff check --fix $(PACKAGES) --exclude "*_pb2*.py"

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

# ============================================================================
# Installation
# ============================================================================

# Install all packages
install:
	@echo "Installing ECG-Streaming packages..."
	$(RUN) uv pip install -e "packages/ecg-common[dev]"
	$(RUN) uv pip install -e "packages/ecg-collector[dev]"
	$(RUN) uv pip install -e "packages/ecg-aggregator[dev]"
	@echo "✓ All packages installed"

# Install without dev dependencies
install-prod:
	@echo "Installing production dependencies..."
	$(RUN) uv pip install -e packages/ecg-common
	$(RUN) uv pip install -e packages/ecg-collector
	$(RUN) uv pip install -e packages/ecg-aggregator
	@echo "✓ Production packages installed"

# Install individual packages
install-common:
	$(RUN) uv pip install -e "packages/ecg-common[dev]"

install-collector:
	$(RUN) uv pip install -e "packages/ecg-collector[dev]"

install-aggregator:
	$(RUN) uv pip install -e "packages/ecg-aggregator[dev]"

# ============================================================================
# Code Generation
# ============================================================================

# Generate gRPC code
proto:
	@echo "Generating gRPC code..."
	$(RUN) python packages/ecg-common/generate_proto.py
	@echo "✓ gRPC code generated"

# ============================================================================
# Cleanup
# ============================================================================

# Clean up generated files
clean:
	@echo "Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -f ecg_data.db 2>/dev/null || true
	@echo "✓ Cleaned up"

# ============================================================================
# Help
# ============================================================================

# Show help
help:
	@echo "ECG Streaming - Development Commands"
	@echo ""
	@echo "Code Quality:"
	@echo "  make fmt         Format code with ruff"
	@echo "  make fmt-check   Check formatting without making changes"
	@echo "  make lint        Run ruff linter"
	@echo "  make lint-fix    Run ruff linter with auto-fix"
	@echo "  make vet         Run mypy type checker"
	@echo "  make check       Run fmt + lint + vet (recommended before commit)"
	@echo "  make check-only  Run lint + vet without formatting"
	@echo "  make test        Run pytest tests"
	@echo ""
	@echo "Installation:"
	@echo "  make install          Install all packages with dev dependencies"
	@echo "  make install-prod     Install only production dependencies"
	@echo "  make install-common   Install ecg-common only"
	@echo "  make install-collector  Install ecg-collector only"
	@echo "  make install-aggregator Install ecg-aggregator only"
	@echo ""
	@echo "Code Generation:"
	@echo "  make proto           Generate gRPC code from .proto files"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean           Remove generated files and caches"
	@echo ""
	@echo "Docker: (see Makefile.docker)"
	@echo "  Development (build locally):"
	@echo "    make docker-build          Build all Docker images"
	@echo "    make docker-up             Start all services (BLE collector)"
	@echo "    make docker-up-usb         Start all services (USB collector)"
	@echo "    make docker-up-aggregator  Start aggregator + frontend only"
	@echo "    make docker-up-collector   Start collector only (BLE mode)"
	@echo ""
	@echo "  Production (use GHCR images):"
	@echo "    make docker-pull           Pull images from GitHub Container Registry"
	@echo "    make docker-prod           Start with pre-built images"
	@echo ""
	@echo "  Management:"
	@echo "    make docker-down           Stop all services"
	@echo "    make docker-logs           Follow logs from all services"
	@echo "    make docker-clean          Stop and remove all containers and volumes"

# ============================================================================
# Include Docker commands
# ============================================================================

include Makefile.docker
