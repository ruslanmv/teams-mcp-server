#!/usr/bin/env bash
set -euo pipefail
ruff check src/ tests/
ruff format --check src/ tests/
