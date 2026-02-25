# Suggested Commands

## Setup
```bash
make venv              # Create virtualenv and install deps
source .venv/bin/activate
```

## Testing
```bash
make test              # Run pytest + pyflakes + integration tests
# Or manually:
PYTHONPATH=. .venv/bin/pytest --cov=kingpin -v
PYTHONPATH=. .venv/bin/pyflakes kingpin
```

## Linting / Formatting
```bash
make lint              # Check formatting (black --diff --check)
DRY=false make lint    # Auto-format (black)
```

## Build
```bash
make build             # Build the package
make pack              # Create a self-contained kingpin.zip
```

## Docs
```bash
make docs              # Build Sphinx docs
```

## Running Kingpin
```bash
kingpin --help
kingpin --dry --script examples/test/sleep.json
kingpin --actor misc.Sleep --option sleep=5 --dry
kingpin --actor misc.Sleep --explain
kingpin --build-only --script examples/simple.json
```

## Git (Darwin system)
Standard `git`, `ls`, `grep`, `find` commands work as expected on macOS.
