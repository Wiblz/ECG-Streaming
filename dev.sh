#!/usr/bin/env bash
# dev.sh — development tooling (format, lint, type check, test, install)
# Usage: ./dev.sh <command>

set -euo pipefail

VENV=".venv/bin/activate"
PACKAGES="packages/ecg-common packages/ecg-collector packages/ecg-aggregator packages/ecg-simulator"

run() {
    # shellcheck source=/dev/null
    source "$VENV" && "$@"
}

cmd="${1:-help}"
shift || true

case "$cmd" in
    fmt)
        echo "==> Formatting code..."
        run ruff format $PACKAGES
        ;;
    lint)
        echo "==> Linting code..."
        run ruff check --fix $PACKAGES --exclude "*_pb2*.py"
        ;;
    vet)
        echo "==> Type checking..."
        run mypy $PACKAGES
        ;;
    check)
        echo "==> Running all checks..."
        run ruff format $PACKAGES
        run ruff check --fix $PACKAGES --exclude "*_pb2*.py"
        run mypy $PACKAGES
        echo "==> All checks passed."
        ;;
    test)
        echo "==> Running tests..."
        run pytest -v "$@"
        ;;
    proto)
        echo "==> Generating gRPC code..."
        run python packages/ecg-common/generate_proto.py
        echo "==> Done."
        ;;
    install)
        echo "==> Installing packages..."
        source "$VENV"
        uv pip install -e "packages/ecg-common[dev]"
        uv pip install -e "packages/ecg-collector[dev]"
        uv pip install -e "packages/ecg-aggregator[dev]"
        uv pip install -e "packages/ecg-simulator[dev]"
        echo "==> Done."
        ;;
    clean)
        echo "==> Cleaning..."
        find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
        find . -type f -name "*.pyc" -delete
        find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
        find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
        find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
        find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
        echo "==> Done."
        ;;
    help|*)
        echo "Usage: ./dev.sh <command>"
        echo ""
        echo "Commands:"
        echo "  fmt       Format code with ruff"
        echo "  lint      Lint and auto-fix with ruff"
        echo "  vet       Type check with mypy"
        echo "  check     Run fmt + lint + vet"
        echo "  test      Run tests (extra args passed to pytest)"
        echo "  proto     Generate gRPC code from .proto files"
        echo "  install   Install all packages with dev dependencies"
        echo "  clean     Remove caches and generated files"
        ;;
esac
