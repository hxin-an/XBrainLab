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
    - now narrowed further: `A01T.gdf` imports with generated names like `EEG-0`, `EEG-1`, ... and `load_gdf_file()` now emits an explicit repo warning about the MNE auto-rename dependency
    - remaining decision: normalize these channel names more intentionally, or expose the ambiguity more formally to downstream workflows
  - the public real-data baseline is now broader in source and format coverage:
    - public local-only fixtures now span PhysioNet, BBCI, SCCN, and MNE testing-data
    - the IO integration slice now targets EDF, GDF, EEGLAB `.set`, CNT, and BrainVision `.vhdr`
    - remaining dataset-validation gap is no longer basic format diversity, but label-attached dataset generation and downstream training smoke on those baselines
  - unattended UI pytest in the current `/mnt/d` Codex workspace now has a clearer blocker than the older capture note:
    - heartbeat-style runs can abort in `pytest-qt` `qapp` setup unless Qt is forced into offscreen mode and matplotlib gets a writable temp cache
    - `scripts/dev/run_ui_pytest.sh` now captures that workaround for repo-local reuse
    - the older `fd`-capture teardown failure is still real; the new quality dashboard re-hit it on `tests/integration/io/test_io_integration.py`, so it remains an active triage item rather than retired history
  - AI assistant local startup now respects saved settings, preflights local runtime, and falls back from unusable CUDA to CPU, but the local-only path still needs a local model cache and final bootstrap validation
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
  - concise human doc entry points under `docs/index.md` and `docs/current/`
  - a thesis-facing report surface under `docs/thesis/`
  - clear thesis-facing direction for future tool-call agent redesign under `docs/decisions/`
  - explicit shared-control-surface definition for the in-app assistant
  - make the next tool-redesign step an audit of the current tool surface against workflow intent and human/agent alignment
  - repo-local skills under `.agents/skills/`
  - Docs MCP configuration and heartbeat automation alignment
  - explicit unattended UI test commands for heartbeat-safe validation

### AQ-PREP-007 Add a reusable quality dashboard and monitoring entrypoint

- Status: Done
- Why:
  Stabilization work now needs one place that answers "is the app still healthy?" without rereading multiple scattered logs.
- Evidence:
  - `/home/administrator/.local/bin/poetry run python scripts/dev/update_quality_dashboard.py`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/integration/ui/test_dialog_acceptance.py -q`
  - `/home/administrator/.local/bin/poetry run python scripts/dev/run_tests.py ui`
- Result:
  - repo-local dashboard generator now writes live reports under `artifacts/quality/`
  - `docs/current/QUALITY_DASHBOARD.md` is the stable human entry point for the live quality report
  - the dashboard now monitors ruff, mypy, architecture compliance, startup smoke, UI baseline capture, dialog acceptance, UI unit suite, and real-data IO integration
  - the expanded dashboard now exposes three concrete red gates instead of one vague "health feels off" signal:
    - repo-wide ruff failures
    - repo-wide mypy failures
    - default-capture real-data IO integration is still not trustworthy in this workspace
  - the generated artifacts stay out of normal git noise via `artifacts/quality/.gitignore`

### AQ-PREP-008 Turn UI baseline checking into a true regression gate

- Status: Done
- Why:
  The dashboard can currently prove that the UI renders and that baseline artifacts are not black, but it still cannot tell us whether accepted layout or visibility structure has drifted.
- Result:
  - the current "correct baseline" is now explicit:
    - structural acceptance criteria live in `docs/workflows/UI_BASELINE.md`
    - approved reference screenshots live in `tests/baselines/ui/`
    - live observed screenshots live in `artifacts/ui/`
  - the shell, five top-level panels, and AI assistant open-shell state now compare against approved reference images instead of only `exists + not black`
  - the quality dashboard wording now reflects that this is a real reference-backed regression gate for the captured core screens, while still not claiming full-app visual coverage

### AQ-PREP-009 Triage static quality-gate failures now exposed by the dashboard

- Status: In progress
- Why:
  Now that static quality checks are part of the dashboard, prep work needs to decide which red gates are immediate blockers and which belong to later cleanup.
- Current focus:
  - repo-wide `ruff check .` currently fails with `21 errors`, `10` auto-fixable
  - repo-wide `mypy XBrainLab/` currently fails with `7 errors in 5 files`
  - decide whether these should be prep-exit blockers or repair-loop backlog items
  - keep the dashboard honest without silently weakening the gates

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
