# Development Guide

## Quick Reference

```bash
./dev.sh fmt      # Format code
./dev.sh lint     # Lint and auto-fix
./dev.sh vet      # Type check
./dev.sh check    # Run all (fmt + lint + vet)
./dev.sh test     # Run tests
```

## Setup

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install packages
uv venv
./dev.sh install
```

## Pre-Commit Workflow

```bash
./dev.sh check
```

This formats, lints, and type-checks all packages in one step.

## Tools

### Ruff (Formatter + Linter)

```bash
./dev.sh fmt       # Format all packages
./dev.sh lint      # Lint with auto-fix
```

Direct usage:
```bash
source .venv/bin/activate
ruff format packages/
ruff format --check packages/   # Check without modifying
ruff check --fix packages/
```

### Mypy (Type Checker)

```bash
./dev.sh vet
```

Direct usage:
```bash
source .venv/bin/activate
mypy packages/ecg-aggregator
```

### Pytest

```bash
./dev.sh test                    # All tests
./dev.sh test -k test_something  # Filter tests
```

## Configuration

All tool configuration is in `pyproject.toml`:
- `[tool.ruff]` — formatter and linter settings
- `[tool.mypy]` — type checker settings
- `[tool.pytest.ini_options]` — test settings

## Code Generation

```bash
./dev.sh proto   # Regenerate gRPC code from .proto files
```

## Cleanup

```bash
./dev.sh clean   # Remove caches and generated files
```

## IDE Integration

### VS Code

```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll": true,
      "source.organizeImports": true
    }
  },
  "python.linting.mypyEnabled": true
}
```

### PyCharm

Settings → Tools → Ruff → Enable formatter and linter

## Ignoring Issues

```python
# Ruff formatting
# fmt: off
code = "not formatted"
# fmt: on

# Ruff linting
import os  # noqa: F401

# Mypy
value = something()  # type: ignore
```

## Stack Management

See `DOCKER_QUICKSTART.md` and `./stack.sh help` for running the full system.
