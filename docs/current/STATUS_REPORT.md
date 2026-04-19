# XBrainLab Status Report

Last updated: `2026-04-19`

This report mirrors the agreed long-running thesis plan so the user can quickly see what has already moved, what was validated, and what is next.

## Snapshot

- Current phase: `Prep Gate`
- Active branch: `codex/stabilization-autopilot`
- Heartbeat cadence: every 10 minutes in this thread
- Thesis direction: stabilize first, redesign the tool-call agent second, validate rigorously throughout
- Active design home: `docs/decisions/`

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
- human-facing docs are now separated into active working docs plus secondary guide/archive areas
- the reviewed official and high-signal skill-selection background now lives in `docs/archive/reference/AGENT_SKILLS.md`
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
- keep the human-facing doc entry points small and easier to scan

## 3. Prep Gate Before Stable Bug Fixing

Plan goal:
- finish all prerequisites needed before shifting into steady bug-fixing and larger backend/test-infra cleanup

What has been done:
- the black screenshot problem was fixed by switching the capture helper to Qt-based grabs
- the UI baseline now captures the shell, all five main panels, and the AI assistant open state:
  - `artifacts/ui/main-window-initial.png`
  - `artifacts/ui/panel-dataset.png`
  - `artifacts/ui/panel-preprocess.png`
  - `artifacts/ui/panel-training.png`
  - `artifacts/ui/panel-evaluation.png`
  - `artifacts/ui/panel-visualization.png`
  - `artifacts/ui/ai-assistant-open.png`
- public cross-format EEG fixtures were added as local-only downloads under `tests/data/public/`:
  - PhysioNet EDF
  - BBCI GDF
  - SCCN EEGLAB `.set`
- IO integration coverage now exercises both the existing repo fixtures and the downloaded public fixtures
- local-only operating assumptions were documented, including the current `pytest --capture=sys` workaround for `fd` capture teardown failures
- top-level shell and panel happy paths now have runtime evidence from the Qt integration slice, not only from screenshots
- the four highest-priority prep-gate dialogs now have headless acceptance coverage through a dedicated Qt integration slice:
  - `LabelMappingDialog`
  - `EventFilterDialog`
  - `EpochingDialog`
  - `TrainingSettingDialog`
- shared refresh propagation now has direct bridge-level smoke coverage for the highest-value downstream paths:
  - dataset events -> `PreprocessPanel`
  - dataset events -> `TrainingPanel`
  - `training_stopped` -> `EvaluationPanel`
  - `training_stopped` -> `VisualizationPanel`
- the user has explicitly approved intentional redesign of the AI assistant panel, which removes the previous design-freeze constraint for that surface only
- the AI assistant startup path now honors saved settings on first initialization and front-loads local-runtime readiness checks instead of deferring them to backend load
- the current Poetry environment now includes the optional `llm` group, and the local backend now probes CUDA usability before model load so it can fall back to CPU when this host's GPU cannot actually execute PyTorch work

Evidence:
- five-panel baseline capture succeeds in `xvfb-run`
- AI assistant baseline capture now also succeeds in `xvfb-run`
- `tests/unit/scripts/test_capture_ui_baseline.py` currently passes with `4 passed`
- `tests/integration/ui/test_e2e_qtbot.py` currently passes with `20 passed`
- `tests/integration/ui/test_dialog_acceptance.py` currently passes with `4 passed`
- `tests/unit/ui/test_panel_event_bridges.py` currently passes with `4 passed`
- `tests/unit/scripts/test_capture_ui_baseline.py tests/integration/io/test_io_integration.py` currently passes with `27 passed, 7 warnings`
- `tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py` currently passes with `35 passed`
- `tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/dialogs/test_model_settings.py` currently passes with `56 passed`
- `tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py` currently passes with `50 passed`
- the downloaded public fixtures load through the direct IO path and the facade import path
- `/home/administrator/.local/bin/poetry install --with llm --no-interaction` completed successfully in the current workspace

Open prep items:
- deepen runtime workflow evidence beyond top-level panel navigation and dock toggling
- convert the remaining runtime warnings/signals into confirmed bugs or confirmed non-blockers
- repair or fully root-cause the default `pytest` capture teardown failure
- complete the remaining local-only AI bootstrap work so this workspace can actually start the assistant locally with a real downloaded model

## 4. Repair Loop

Plan goal:
- once prep is complete, move into the long-running bug-fix / test / docs / backend-refactor loop

Current status:
- not started as the primary phase yet because `Prep Gate` is still incomplete
- a few repair-loop enablers are already in place, especially broader dataset-format coverage and a stronger capture baseline

What will unlock this phase:
- prep gate completion across workflow baselines, dialog checks, smoke protections, and runtime-signal triage

## 5. Tool-Call Agent Redesign

Plan goal:
- turn the future tool-call agent redesign into a thesis-grade design track instead of a loose pile of ideas

What has been done:
- `AGENTS.md` now records that this repository is the implementation workspace for the user's master's thesis
- `docs/decisions/README.md` now acts as the decision-record entry point
- `docs/decisions/ADR-011-thesis-direction.md` now captures the current thesis order of work:
  - stabilization first
  - tool-call agent redesign second
  - rigorous validation throughout
- `docs/decisions/ADR-012-project-structure-redesign.md` now records the proposed repository and documentation information architecture redesign needed before the next major architecture phase

What is next:
- evaluate the existing ADR set against the current codebase and identify which agent-design assumptions are still valid
- add new redesign ADRs under `docs/decisions/` instead of scattering architecture notes across multiple folders

## 6. Rigorous Validation

Plan goal:
- make validation a first-class thesis deliverable rather than something deferred until after implementation

What has been done:
- the current plan now explicitly separates stabilization, agent redesign, and rigorous validation into visible workstreams
- the doc entry points now make it clearer where future experiment and decision work should live

What is next:
- define the evaluation structure for the redesigned tool-call agent
- connect future claims to tests, runtime evidence, or documented experiment plans

## Current Risks

- default `pytest` `fd` capture still fails in this workspace; `--capture=sys` is the current validated workaround
- real GDF fixtures still emit duplicate-channel-name warnings
- the public BBCI `O3VR.gdf` fixture emits an MNE annotation-range warning even though import succeeds
- the AI assistant now front-loads local-runtime failure more cleanly and can fall back away from unusable CUDA, but this workspace still lacks a cached local model for actual local startup
- the current AI assistant direction is local-only startup, so model/bootstrap readiness is now the main explicit blocker rather than something to route around with Gemini
- broader dialog realism is better than before, but the global `QDialog.exec` patch still means desktop-manual behavior is not identical to the unit harness

## Immediate Next Moves

1. keep this report synced to the plan after each meaningful cycle
2. continue prep-gate work on runtime-signal triage and deeper workflow sequences beyond shell-level navigation
3. continue local-only AI bootstrap work by validating a real local model path and tightening any remaining end-to-end startup gaps
4. begin consolidating existing agent ADRs into a smaller thesis-ready redesign path under `docs/decisions/`
