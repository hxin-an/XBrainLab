---
name: xbrainlab-real-data-validation
description: Use when validating XBrainLab against real EEG data and cross-format fixtures. Trigger for dataset import checks, facade import checks, public fixture downloads, GDF/EDF/BDF/FIF/BrainVision/EEGLAB format validation, or warning triage tied to real files.
---

# XBrainLab Real Data Validation

Use this skill when validation must be grounded in real EEG files rather than toy mocks.

## Read First

1. `AGENTS.md`
2. `.agents/stack.md`
3. `.agents/runbooks/setup.md`
4. `.agents/runbooks/autopilot.md`
5. `.agents/runbooks/active-queue.md`
6. `docs/current/BUG_TRIAGE.md`
7. `docs/current/STATUS_REPORT.md`
8. `docs/history/SESSION_LOG.md`

## Scope

Focus on:

- raw loader behavior
- facade import behavior
- format coverage across real fixtures
- warnings that show up only on authentic data
- public local-only fixture maintenance under `tests/data/public/`

## Working Pattern

1. Prefer existing real fixtures first.
2. Use the local public-fixture set when broader format coverage is needed.
3. Distinguish between blocking import failures and non-blocking warnings.
4. Convert recurring warnings into explicit triage records or regression tests.

## Validation Commands

- `/home/administrator/.local/bin/poetry run python scripts/dev/fetch_public_eeg_fixtures.py`
- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`

## Recordkeeping

After meaningful progress, update:

- `docs/current/BUG_TRIAGE.md`
- `docs/current/STATUS_REPORT.md`
- `docs/history/SESSION_LOG.md`
- `.agents/runbooks/active-queue.md`
