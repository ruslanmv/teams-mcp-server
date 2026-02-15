#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$(pwd)/src"
uvicorn teams_mcp.main:app --host "${TEAMS_MCP_HOST:-0.0.0.0}" --port "${TEAMS_MCP_PORT:-9106}" --reload
