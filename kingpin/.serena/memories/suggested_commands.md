# Kingpin — Suggested Commands

## Prerequisites
- **uv** must be installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Environment Setup
```bash
# Install all dependencies (creates .venv automatically)
make venv
# Or directly:
uv sync
```

## Running Tests
```bash
# Full test suite (pytest + pyflakes + dry-run deploy examples)
make test

# Just pytest with coverage
PYTHONPATH=. uv run pytest --cov=kingpin -v

# Run a specific test file
PYTHONPATH=. uv run pytest kingpin/actors/test/test_base.py -v

# Run a specific test
PYTHONPATH=. uv run pytest kingpin/actors/test/test_base.py::TestClassName::test_method -v

# Pyflakes lint check
PYTHONPATH=. uv run pyflakes kingpin
```

## Formatting & Linting
```bash
# Check formatting (dry run, no changes)
make lint

# Apply formatting
DRY=false make lint

# Or directly:
uv run black kingpin                  # apply
uv run black --diff --check kingpin   # check only
```

## Building
```bash
# Build distribution
make build

# Build self-contained zip
make pack
```

## Running Kingpin
```bash
# Dry-run with a script
PYTHONPATH=. uv run python kingpin/bin/deploy.py --dry --script examples/test/sleep.json

# Or via installed entry point (after `uv sync`)
uv run kingpin --dry --script examples/test/sleep.json
```

## Documentation
```bash
# Build Sphinx docs
make docs
```

## Cleaning
```bash
make clean
```

## System Utilities (macOS/Darwin)
```bash
git status / git diff / git log   # version control
ls / find / grep                   # file operations (use Serena tools when possible)
uv run python                      # run Python in the project venv
```
