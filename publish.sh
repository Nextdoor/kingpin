#!/bin/bash -x
#
# Quick script for publishing the module to PyPI.
#

if [ -z `which pandoc` ]; then
  echo "You must have Pandoc installed. See https://github.com/jgm/pandoc/releases."
  exit 1
fi

# Convert the README from Markdown to RST
pandoc --from=markdown --to=rst --output=README.txt README.md

# Build the package
python setup.py sdist upload

# Clean up
rm -f README.txt
