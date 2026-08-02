#!/usr/bin/env bash
set -euo pipefail

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export MPLBACKEND="${MPLBACKEND:-Agg}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-codex}"
mkdir -p "${MPLCONFIGDIR}"

result_json="${XBL_PYTEST_RESULT_JSON:-}"
cleanup_result=""
if [[ -z "${result_json}" ]]; then
    result_json="$(mktemp "${TMPDIR:-/tmp}/xbrainlab-ui-pytest-XXXXXX.json")"
    rm -f "${result_json}"
    cleanup_result="${result_json}"
fi
if [[ -n "${cleanup_result}" ]]; then
    trap 'rm -f "${cleanup_result}"' EXIT
fi

/home/administrator/.local/bin/poetry run -- python \
    -m scripts.dev.run_required_pytest_gate \
    --result-json "${result_json}" \
    -- --capture=sys "$@"
