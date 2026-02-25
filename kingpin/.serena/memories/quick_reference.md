# Kingpin Quick Reference

## Purpose
Kingpin is a **Deployment Automation Engine** by Nextdoor. It provides API abstraction, an async automation engine (Tornado), and parallel execution via a JSON/YAML DSL.

## Tech Stack
- **Language**: Python 3.7+
- **Async Framework**: Tornado (coroutines with `@gen.coroutine` + `yield`)
- **AWS SDK**: boto3/botocore
- **Templating**: JSON/YAML with token replacement (`%TOKEN%` and `{CONTEXT}`)
- **Testing**: pytest + mock + tornado.testing
- **Formatting**: black
- **Linting**: pyflakes
- **Docs**: Sphinx + ReadTheDocs

## Entry Point
`kingpin/bin/deploy.py:begin()` → CLI via `kingpin` command (pyproject.toml `[project.scripts]`)

## Key Modules
- `kingpin/bin/deploy.py` - CLI entry point
- `kingpin/actors/base.py` - BaseActor, EnsurableBaseActor, HTTPBaseActor
- `kingpin/actors/group.py` - Sync, Async group actors
- `kingpin/actors/misc.py` - Macro, Sleep, Note, GenericHTTP
- `kingpin/actors/aws/` - AWS actors (CloudFormation, IAM, S3)
- `kingpin/actors/hipchat.py`, `rollbar.py`, `librato.py` - Third-party integrations
- `kingpin/utils.py` - Token replacement, JSON/YAML loading, logging
- `kingpin/schema.py` - JSON Schema validation for DSL
- `kingpin/constants.py` - REQUIRED, STATE, SchemaCompareBase

## Version
5.0.0 (in `kingpin/version.py`)
