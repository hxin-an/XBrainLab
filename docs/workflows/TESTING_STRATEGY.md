# XBrainLab Testing Strategy For Stabilization

This document defines the practical testing strategy for the stabilization phase of this project.

It complements the broader development docs, but is optimized for bug fixing and repeated local validation in WSL2.

## Principles

- test the smallest thing that proves the fix
- keep shared UI regressions visible
- separate behavioral validation from visual/layout validation
- prefer repeatable headless workflows by default

## Environment Baseline

Validated in WSL2 `Ubuntu-24.04`:

- `/home/administrator/.local/bin/poetry`
- `pytest`
- `pytest-qt`
- `xvfb-run`
- `xdotool`
- `scrot`

## Fast Command Reference

Run from `/home/administrator/repos/XBrainLab`:

```bash
# Launch app normally
/home/administrator/.local/bin/poetry run python run.py

# Launch app headless with virtual display
xvfb-run -a /home/administrator/.local/bin/poetry run python run.py

# Focused UI suite
/home/administrator/.local/bin/poetry run pytest tests/unit/ui -q

# Integration UI slice
/home/administrator/.local/bin/poetry run pytest tests/integration/ui -q

# Full test suite
/home/administrator/.local/bin/poetry run pytest
```

Current Codex local note for `/mnt/d/repos/XBrainLab`:

- default `pytest` capture is currently unreliable in this workspace and can fail during teardown
- until that is repaired, prefer `-s` for local validation commands inside this Codex workspace
- keep the original commands as the baseline reference for the canonical WSL setup

## Three Validation Layers

### 1. Focused regression tests

Use when fixing a specific bug.

Examples:

```bash
/home/administrator/.local/bin/poetry run pytest tests/unit/ui/test_main_window.py -q
/home/administrator/.local/bin/poetry run pytest tests/unit/ui/test_model_summary.py::TestModelSummaryWindow::test_on_plan_select_success -q
```

This is the first thing to run before and after a fix.

### 2. Shared UI safety pass

Use when changing:

- `main_window`
- shared UI core classes
- styles
- panel lifecycle logic
- common dialogs

Command:

```bash
/home/administrator/.local/bin/poetry run pytest tests/unit/ui -q
```

This is our minimum anti-regression net for PyQt work.

### 3. Workflow smoke validation

Use when changes cross panel boundaries or affect startup.

Suggested commands:

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run python run.py
/home/administrator/.local/bin/poetry run pytest tests/integration/ui -q
```

## Visual And Layout Validation

Existing tests mostly validate behavior, not layout correctness.

For layout-sensitive work, use this manual-plus-artifact flow:

1. Launch with `xvfb-run`.
2. Reproduce the screen state.
3. Capture screenshots with `scrot`.
4. Compare against the expected layout checklist in `docs/workflows/UI_BASELINE.md`.

Suggested artifact directory:

```text
artifacts/ui/
```

If we decide to automate screenshot comparisons later, this directory can become the baseline store.

Suggested capture pattern:

```bash
mkdir -p artifacts/ui
xvfb-run -a /home/administrator/.local/bin/poetry run python run.py
# then use scrot or a focused helper script to save screenshots into artifacts/ui
```

Helper script:

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py
```

The helper now captures:

- `main-window-initial.png`
- `panel-dataset.png`
- `panel-preprocess.png`
- `panel-training.png`
- `panel-evaluation.png`
- `panel-visualization.png`

Optional public-fixture fetch step for broader cross-dataset validation:

```bash
/home/administrator/.local/bin/poetry run python scripts/dev/fetch_public_eeg_fixtures.py
```

## Known Constraints

### VTK and visualization instability

Some tests are intentionally skipped in headless environments because VTK/Qt state can become unstable.

Implications:

- do not treat skipped visualization tests as a fresh failure by default
- isolate visualization work
- validate those changes with focused runs and explicit evidence

### Global test patching

`tests/conftest.py` globally patches blocking dialogs and mocks some visualization modules.

Implications:

- unit tests are not identical to a full interactive session
- passing tests do not guarantee a perfect real desktop experience
- manual smoke checks still matter for modal workflows and rendering-heavy screens

## When To Add New Tests

Add a test when:

- the bug is user-visible and reproducible
- the affected code path can be isolated
- the issue is likely to return during refactors

Do not force a fragile test when:

- the bug is purely visual and the current harness cannot observe it reliably
- the fix is exploratory and the right boundary is not understood yet

In those cases, record the evidence and add a follow-up task to improve observability.

## Minimum Done Criteria For Bug Fixes

A bug fix is not done until:

- the issue has a clear reproduction note or failure signal
- the fix has been validated by the smallest relevant test slice
- shared UI tests are re-run if common UI plumbing changed
- manual validation is performed if the bug affected layout, rendering, or modal flow
