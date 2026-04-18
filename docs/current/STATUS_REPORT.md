# XBrainLab Status Report

Last updated: `2026-04-19`

This report mirrors the agreed long-running plan so the user can quickly see what has already moved, what was validated, and what is next.

## Snapshot

- Current phase: `Prep Gate`
- Active branch: `codex/stabilization-autopilot`
- Heartbeat cadence: every 10 minutes in this thread

## 1. Baseline And Checkpoint

Plan goal:
- collect the current dirty worktree into a stable, verifiable baseline before piling on more work

What has been done:
- the work continued on `codex/stabilization-autopilot` instead of staying on `main`
- the pre-existing in-flight work was preserved rather than reverted
- startup, training-option, main-window sync, capture-helper, and IO slices were rechecked in the current environment

Evidence:
- headless startup smoke reaches `MainWindow initialized`
- prior checkpoint commit exists on this branch: `9a475f3`

What is next:
- keep turning new prep work into small verified checkpoints rather than allowing another large untracked pileup

## 2. Codex Harness And Always-On Loop

Plan goal:
- make the repo runnable by an autopilot loop without losing context or drifting from the agreed workflow

What has been done:
- `AGENTS.md` has been shortened into an entry map instead of a long handbook
- `.agents/stack.md` now explicitly records the selected skills, rule policy, external setup references, and heartbeat reading order
- canonical agent runtime docs now live under `.agents/runbooks/`
- repo-local stabilization skills now live under `.agents/skills/`, including prep-gate, repair-loop, workflow-baseline, dialog-audit, real-data-validation, and refresh-smoke
- `docs/index.md` now acts as the human doc portal instead of a second README-style overview
- human-facing docs are now separated into `docs/current/`, `docs/workflows/`, `docs/history/`, and `docs/reference/`
- `docs/reference/AGENT_SKILLS.md` now records the reviewed official and high-signal ecosystem sources plus the selected skill set
- local Codex config includes the OpenAI Docs MCP endpoint
- the thread heartbeat automation `XBrainLab Autopilot` is active every 10 minutes
- this `docs/current/STATUS_REPORT.md` file is now part of the required work loop

Evidence:
- the canonical agent surface is now under `.agents/`
- `docs/` now separates current-state docs, workflow references, history, and background reference material
- the agent-facing stack is now anchored in `.agents/stack.md`
- the thread heartbeat cadence is set to 10 minutes

What is next:
- keep the heartbeat prompt, status report, and queue aligned as the work evolves

## 3. Prep Gate Before Stable Bug Fixing

Plan goal:
- finish all prerequisites needed before shifting into steady bug-fixing and larger backend/test-infra cleanup

What has been done:
- the black screenshot problem was fixed by switching the capture helper to Qt-based grabs
- the UI baseline now captures the shell plus all five main panels:
  - `artifacts/ui/main-window-initial.png`
  - `artifacts/ui/panel-dataset.png`
  - `artifacts/ui/panel-preprocess.png`
  - `artifacts/ui/panel-training.png`
  - `artifacts/ui/panel-evaluation.png`
  - `artifacts/ui/panel-visualization.png`
- public cross-format EEG fixtures were added as local-only downloads under `tests/data/public/`:
  - PhysioNet EDF
  - BBCI GDF
  - SCCN EEGLAB `.set`
- IO integration coverage now exercises both the existing repo fixtures and the downloaded public fixtures
- local-only operating assumptions were documented, including the current `pytest -s` workaround for capture teardown failures

Evidence:
- five-panel baseline capture succeeds in `xvfb-run`
- `tests/unit/scripts/test_capture_ui_baseline.py tests/integration/io/test_io_integration.py` currently passes with `27 passed, 7 warnings`
- the downloaded public fixtures load through the direct IO path and the facade import path

Open prep items:
- runtime-verify all six major workflows, not just the main shell and IO-heavy paths
- run and record live/modal checks for the highest-risk dialogs
- widen refresh/navigation and cross-panel propagation protection
- convert the remaining runtime warnings/signals into confirmed bugs or confirmed non-blockers
- repair or fully root-cause the default `pytest` capture teardown failure

## 4. Repair Loop

Plan goal:
- once prep is complete, move into the long-running bug-fix / test / docs / backend-refactor loop

Current status:
- not started as the primary phase yet because `Prep Gate` is still incomplete
- a few repair-loop enablers are already in place, especially broader dataset-format coverage and a stronger capture baseline

What will unlock this phase:
- prep gate completion across workflow baselines, dialog checks, smoke protections, and runtime-signal triage

## Current Risks

- default `pytest` capture still fails in this workspace unless tests are run with `-s`
- real GDF fixtures still emit duplicate-channel-name warnings
- the public BBCI `O3VR.gdf` fixture emits an MNE annotation-range warning even though import succeeds

## Immediate Next Moves

1. keep this report synced to the plan after each meaningful cycle
2. continue prep-gate work on workflow baselines and high-risk dialogs
3. triage or repair the default `pytest` capture teardown failure
