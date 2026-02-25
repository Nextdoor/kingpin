# Kingpin — Quick Reference

## Purpose
Kingpin is a **Deployment Automation Engine** built by Nextdoor Engineering. It provides:
- **API Abstraction** — Job instructions via a JSON/YAML-based DSL
- **Automation Engine** — Built on Python's Tornado async framework
- **Parallel Execution** — Non-blocking network IO with parallel actor execution

## Tech Stack
- **Language**: Python 3.9+ (currently targeting 3.13)
- **Async framework**: Tornado 6.x (`tornado.gen` coroutines)
- **AWS SDK**: boto3
- **JSON schema validation**: jsonschema
- **CloudFormation YAML**: cfn-flip
- **Build system**: setuptools (via `pyproject.toml`)
- **Package/dependency manager**: uv (replaces pip/venv)
- **Testing**: pytest + pytest-cov, mock, tornado.testing
- **Linting**: pyflakes
- **Formatting**: black
- **Docs**: Sphinx + ReadTheDocs

## Version
Current version: 5.0.1 (defined in `kingpin/version.py`)

## Entry Point
`kingpin/bin/deploy.py` → CLI command `kingpin`

## Project Structure
```
kingpin/
├── bin/                  # CLI entry point (deploy.py)
├── actors/               # Actor implementations (core abstraction)
│   ├── base.py           # BaseActor, EnsurableBaseActor
│   ├── group.py          # Sync/Async group actors
│   ├── misc.py           # Miscellaneous actors (Macro, etc.)
│   ├── hipchat.py        # HipChat integration
│   ├── librato.py        # Librato integration
│   ├── rollbar.py        # Rollbar integration
│   ├── aws/              # AWS actors
│   │   ├── base.py       # AWS base actor
│   │   ├── cloudformation.py
│   │   ├── iam.py
│   │   ├── s3.py
│   │   ├── api_call_queue.py
│   │   └── settings.py
│   └── test/             # Actor tests
├── test/                 # Top-level tests (version, utils, schema)
├── utils.py              # Shared utilities
├── schema.py             # JSON schema definitions
├── constants.py          # Constants (REQUIRED, STATE, etc.)
├── exceptions.py         # Exception classes
└── version.py            # Version string
```

## Key Architecture
- **Actor pattern**: All actions implement `BaseActor` or `EnsurableBaseActor`
- Actors define `all_options` dict for configuration
- Actors support `dry` mode (no live changes) and `warn_on_failure`
- Context tokens (`{KEY}`) are used for variable substitution in DSL
- Group actors (`group.Sync`, `group.Async`) orchestrate other actors
