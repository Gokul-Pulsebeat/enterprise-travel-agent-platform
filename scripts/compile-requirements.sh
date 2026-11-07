#!/usr/bin/env bash
set -euo pipefail

docker run --rm \
  -v "$(pwd):/workspace" \
  -w /workspace \
  python:3.11-slim \
  bash -c "pip install --no-cache-dir pip-tools && pip-compile --resolver=backtracking requirements.in -o requirements.txt"