# Kingpin — Task Completion Checklist

When a coding task is completed, run through these steps:

## 1. Format the Code
```bash
DRY=false make lint
```
This runs `black` on the `kingpin/` directory.

## 2. Run the Linter
```bash
PYTHONPATH=. uv run pyflakes kingpin
```
Fix any unused imports, undefined names, etc.

## 3. Run the Test Suite
```bash
make test
```
This runs:
- `pytest --cov=kingpin -v` (all tests with coverage)
- `pyflakes kingpin` (static analysis)
- Dry-run deploy of example JSON and YAML scripts

## 4. Verify Test Coverage
- Check that new/modified code is covered by tests
- Tests live alongside source: `kingpin/actors/test/`, `kingpin/test/`, `kingpin/bin/test/`
- Follow the existing pattern: `test_<module>.py` for unit tests

## 5. PR Title Format
If creating a PR, use conventional commit format:
```
type(scope): short description
```
- **Types**: chore, docs, feat, fix, refactor, test
- **Scopes**: deps, docs, ci, actors, aws, s3, iam, cfn, cloudformation, group, macro
- Scope is required
- PRs should be opened in **draft** mode
