# Suggested Commands for Kingpin Development

## Setup
```bash
uv sync                    # Install all dependencies (dev + runtime)
```

## Testing
```bash
make test                  # Full test suite: pytest --cov + pyflakes + smoke tests
PYTHONPATH=. uv run pytest -v kingpin/actors/test/test_base.py  # Single test file
PYTHONPATH=. uv run pytest -v -k "test_name"                    # Single test by name
```

## Linting & Formatting
```bash
make lint                  # Black check (dry run)
DRY=false make lint        # Black format (apply changes)
make ruff                  # Ruff linting
make ruff-fix              # Ruff auto-fix
make mypy                  # Type checking
```

## Building
```bash
make build                 # Build package
make pack                  # Create self-contained kingpin.zip
make docs                  # Build Sphinx documentation
```

## Running
```bash
kingpin --script deploy.json --dry      # Dry run a script
kingpin --actor misc.Sleep -o sleep=5   # Run single actor
kingpin --actor misc.Sleep -E           # Explain an actor
```

## Version & Release
```bash
make bump VERSION=patch    # Bump version, create branch + PR
```

## System Utilities (macOS/Darwin)
```bash
git, ls, cd, grep, find   # Standard Unix utils available
uv                         # Package manager (replaces pip/poetry)
```
