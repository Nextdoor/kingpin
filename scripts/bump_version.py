#!/usr/bin/env python3
"""Bump the version in kingpin/version.py.

Usage:
    python scripts/bump_version.py <major|minor|patch>

Reads the current version from kingpin/version.py, increments the specified
component, writes it back, and prints the old and new versions to stdout as:
    OLD_VERSION=x.y.z
    NEW_VERSION=x.y.z
"""

import logging
import re
import sys

log = logging.getLogger(__name__)

VERSION_FILE = "kingpin/version.py"
VERSION_RE = re.compile(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"')
VALID_PARTS = ("major", "minor", "patch")


def read_current_version():
    with open(VERSION_FILE) as f:
        match = VERSION_RE.search(f.read())
    if not match:
        log.error("Could not parse version from %s", VERSION_FILE)
        sys.exit(1)
    return match.group(1)


def compute_new_version(current, part):
    major, minor, patch = (int(x) for x in current.split("."))

    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    elif part == "patch":
        return f"{major}.{minor}.{patch + 1}"


def write_version(new_version):
    with open(VERSION_FILE) as f:
        content = f.read()
    content = VERSION_RE.sub(f'__version__ = "{new_version}"', content)
    with open(VERSION_FILE, "w") as f:
        f.write(content)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) != 2 or sys.argv[1].strip().lower() not in VALID_PARTS:
        log.error("Usage: %s <major|minor|patch>", sys.argv[0])
        sys.exit(1)

    part = sys.argv[1].strip().lower()
    old = read_current_version()
    new = compute_new_version(old, part)

    log.info("Bumping version: %s -> %s (%s)", old, new, part)
    write_version(new)
    log.info("Updated %s", VERSION_FILE)

    # Print in a format the Makefile can capture (stdout, not logging)
    print(f"OLD_VERSION={old}")
    print(f"NEW_VERSION={new}")


if __name__ == "__main__":
    main()
