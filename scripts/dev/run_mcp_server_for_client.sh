#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
POETRY_BIN="${POETRY_BIN:-}"

if [[ -z "${POETRY_BIN}" ]]; then
    if command -v poetry >/dev/null 2>&1; then
        POETRY_BIN="$(command -v poetry)"
    elif [[ -x "${HOME}/.local/bin/poetry" ]]; then
        POETRY_BIN="${HOME}/.local/bin/poetry"
    else
        echo "Could not find poetry for the prepared XBrainLab runtime." >&2
        exit 127
    fi
fi

cd "${REPO_ROOT}"
exec "${POETRY_BIN}" run python scripts/dev/run_mcp_server.py
