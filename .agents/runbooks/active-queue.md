# XBrainLab Active Queue

This is the ordered queue for unattended Codex work.

The topmost eligible item should be worked on first.

## Phase

- Current phase: `Prep Gate`
- Exit rule: do not begin normal repair queue work until `Prep Complete` criteria in `.agents/runbooks/autopilot.md` are all satisfied

## Active Prep Gate

### AQ-PREP-002 Verify top-level panel happy paths in headless mode

- Status: Done
- Why:
  The workflow map needs observed runtime evidence, not just code reading.
- Target screens:
  - Dataset
  - Preprocess
  - Training
  - Evaluation
  - Visualization
  - AI assistant shell
- Evidence:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/scripts/test_capture_ui_baseline.py -q`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q`
- Result:
  - shell, all five primary panels, and `ai-assistant-open.png` now have headless baseline artifacts
  - the nav and AI-dock integration slice passed with `20 passed`
  - the same integration run also exposed a new AI-shell runtime signal for local model initialization, which now belongs in triage

### AQ-PREP-003 Audit high-risk dialog acceptance flows

- Status: Done
- Why:
  Dialog-heavy workflows remain one of the biggest risks because unit tests mock many modal paths.
- Priority dialogs:
  - `LabelMappingDialog`
  - `EventFilterDialog`
  - `EpochingDialog`
  - `TrainingSettingDialog`
- Evidence:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_dialog_acceptance.py -q`
- Result:
  - the four priority dialogs now have headless button-driven acceptance coverage
  - the acceptance slice validates real widget state changes plus the OK-button path instead of only direct method calls
  - the remaining modal realism caveat is now narrower: `QDialog.exec` is still patched in the broader unit harness, but these four dialogs are no longer relying only on mocked coverage

### AQ-PREP-004 Expand refresh and navigation smoke protection

- Status: Done
- Why:
  Shared refresh coupling is a system-wide risk and must be stronger before deeper UI-adjacent fixes.
- Current focus:
  - downstream panel propagation checks after shared events
  - keep `MainWindow.switch_page()` behavior covered
  - preserve target-panel-only refresh behavior
- Evidence:
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/ui/test_main_window_sync.py -q`
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/ui/test_panel_event_bridges.py -q`
- Result:
  - `switch_page()` remains covered for target-panel-only refresh behavior
  - dataset events now have direct bridge-level smoke coverage into `PreprocessPanel` and `TrainingPanel`
  - `training_stopped` propagation now has direct bridge-level smoke coverage into `EvaluationPanel` and `VisualizationPanel`

### AQ-PREP-005 Triage remaining runtime signals into concrete bug IDs

- Status: In progress
- Why:
  The prep gate is not complete until current runtime signals are either fixed or converted into actionable bug records.
- Current focus:
  - duplicate EEG channel-name warnings in real GDF workflows
  - pytest default capture teardown failure in the current `/mnt/d` Codex workspace
  - AI assistant local-model initialization failing because `accelerate` is missing in the current environment
  - visualization headless fragility and skip boundaries

### AQ-PREP-006 Clarify local-only and Codex operating assumptions

- Status: In progress
- Why:
  Long-running unattended work needs durable repo docs and reliable local Codex setup.
- Current focus:
  - short repo-root `AGENTS.md`
  - `.agents/stack.md`
  - `.agents/runbooks/setup.md`
  - `.agents/runbooks/autopilot.md`
  - repo-local skills under `.agents/skills/`
  - Docs MCP configuration and heartbeat automation alignment

## Recently Completed

### AQ-PREP-001 Fix black screenshot baseline output

- Status: Done
- Result:
  the capture helper now grabs the rendered Qt main window directly instead of relying on a black-prone virtual-display screenshot path
- Evidence:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - artifact: `artifacts/ui/main-window-initial.png`

## Repair Queue

Begin these only after `Prep Complete`.

### AQ-001 Strengthen dataset import and label import reliability

- Status: Ready after prep
- Why:
  Dataset import remains the highest-value repair surface once the prep gate is cleared.

### AQ-002 Improve preprocess readiness and downstream state propagation

- Status: Ready after prep
- Why:
  Preprocess state drives training readiness and downstream workflow coherence.

### AQ-003 Stabilize training state synchronization

- Status: Ready after prep
- Why:
  Training events fan out into logs, plots, evaluation, and visualization.

### AQ-004 Tighten evaluation consistency

- Status: Ready after prep
- Why:
  Evaluation depends on cross-screen state alignment after training completes.

### AQ-005 Stabilize visualization validation and runtime behavior

- Status: Ready after prep
- Why:
  Visualization remains the highest-risk user-facing area once core flows are stable.

### AQ-006 Remove or demote remote API dependencies from user-facing flows

- Status: Ready after prep
- Why:
  The longer-term target remains local-model-first operation rather than OpenAI/Gemini dependency.

## Deferred

### DQ-001 Broad UI redesign

- Status: Deferred
- Reason:
  The user wants intentional design changes discussed first.

### DQ-002 Large architecture rewrite outside backend/test-infra stabilization

- Status: Deferred
- Reason:
  More runtime evidence is needed before choosing broad restructuring.
