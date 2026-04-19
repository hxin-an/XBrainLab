# XBrainLab Active Queue

This is the ordered queue for unattended Codex work.

The topmost eligible item should be worked on first.

## Phase

- Current phase: `Repair Loop`
- Entry basis: `Prep Complete` was re-established on `2026-04-19` after the fast dashboard refreshed to `PASS`: six-workflow shell baselines are now host-safe, `ruff` and `basedpyright` are green again, and the trusted real-data IO dashboard slice now uses the workspace-safe `--capture=sys` command
- Queue rule: work the top repair item first; reopen prep only if a prep-exit criterion turns red again with fresh evidence

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
  - `timeout 25s xvfb-run -a /home/administrator/.local/bin/poetry run python run.py`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/scripts/test_capture_ui_baseline.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/integration/ui/test_e2e_qtbot.py -q`
- Result:
  - startup still reaches `MainWindow initialized`, and baseline capture still regenerates shell, all five primary panels, and `ai-assistant-open.png`
  - the saved screenshots remain usable non-black artifacts, so the shell plus all five primary panels still have fresh visual evidence
  - the AI-dock toggle case inside `tests/integration/ui/test_e2e_qtbot.py` now stubs `AgentManager.start_system()` so the six-screen baseline validates shell-open behavior without triggering local-model bootstrap
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/integration/ui/test_e2e_qtbot.py -q` now passes at `20 passed`, so the six main workflows are again runtime-verified by a host-safe accepted slice
  - the risky local-backend bootstrap path remains tracked separately under `BUG-AGENT-001`; it is no longer mixed into Prep Gate's shell-level workflow evidence

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

- Status: Done
- Why:
  The prep gate is not complete until current runtime signals are either fixed or converted into actionable bug records.
- Evidence:
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py -q`
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... LLMConfig.load_from_file() ... PY`
- Result:
  - the real GDF duplicate-name warning is now a concrete dataset bug record under `BUG-DATASET-007`; the ambiguity remains unresolved, but it is no longer only a vague third-party warning because `Raw` wrappers now retain the signal explicitly
  - the default-capture teardown issue remains under `BUG-ENV-003`, but the accepted workspace-safe command is now `--capture=sys`, and the fast dashboard has been aligned to that trusted path instead of treating flaky `fd` capture as current gate truth
  - unattended UI pytest remains concretely blocked by `BUG-ENV-004`, with `scripts/dev/run_ui_pytest.sh` as the documented unattended-safe workaround
  - AI assistant local startup remains under `BUG-AGENT-001`; persisted settings, preflight checks, and CUDA fallback are now in place, and the remaining concrete blocker is missing local model cache for `Qwen/Qwen2.5-7B-Instruct`
  - the visualization headless signal was successfully narrowed under single `BUG-ENV-001` during prep: `TestSaliency3DEngine` was green, collection-time pollution was isolated, and the remaining redesign-suite surface was recognized as stale coverage rather than a second confirmed VTK runtime bug; that narrowed surface was then fully repaired later under `AQ-005`
  - the broader public-fixture baseline is no longer a runtime-signal blocker in this queue item; the remaining gap there is validation depth rather than missing bug framing

### AQ-PREP-006 Clarify local-only and Codex operating assumptions

- Status: Done
- Why:
  Long-running unattended work needs durable repo docs and reliable local Codex setup.
- Evidence:
  - `ls docs/thesis && test -f docs/index.md && test -f .agents/stack.md && test -f .agents/runbooks/setup.md && test -f .agents/runbooks/autopilot.md && test -d .agents/skills`
- Result:
  - repo-local Codex operating assumptions are now documented in `AGENTS.md`, `.agents/stack.md`, `.agents/runbooks/setup.md`, `.agents/runbooks/autopilot.md`, `.agents/runbooks/pending-sync.md`, and `.agents/roles/executor.md`
  - human-facing entry points now exist under `docs/index.md`, `docs/current/`, `docs/thesis/`, and `docs/decisions/`, so the local-only thesis workflow is no longer implicit or scattered
  - Docs MCP selection, repo-local skills, automation reading order, pending-sync fallback, and unattended-safe UI validation commands are all written down in repo docs rather than living only in session memory

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
  - the dashboard now exposes concrete gate truth instead of one vague "health feels off" signal; the latest direct fast refresh is fully green, while slower `mypy` debt remains intentionally outside the default profile
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
  - after `AQ-006` changed the assistant shell to local-first wording, the approved `ai-assistant-open.png` reference was re-promoted to the current accepted shell state so the fast dashboard once again reflects true baseline health instead of stale Gemini-era reference drift

### AQ-PREP-009 Triage static quality-gate failures now exposed by the dashboard

- Status: Done
- Why:
  Now that static quality checks are part of the dashboard, prep work needs to decide which red gates are immediate blockers and which belong to later cleanup.
- Evidence:
  - `/home/administrator/.local/bin/poetry run ruff check .`
  - `/home/administrator/.local/bin/poetry run basedpyright`
  - `/home/administrator/.local/bin/poetry run mypy XBrainLab/`
  - `/home/administrator/.local/bin/poetry run python tests/architecture_compliance.py`
- Result:
  - the static-gate triage decision remains explicit: fast static gates are prep-exit blocking, but the current direct reruns are now green again
  - `ruff check .` now passes, `basedpyright` remains green at `0 errors, 0 warnings, 0 notes`, and `python tests/architecture_compliance.py` continues to pass
  - `mypy XBrainLab/` remains the slower monitored debt gate, so it stays visible without being treated as the same kind of high-frequency blocker as the fast gate
  - with the fast static gate restored and the refreshed fast dashboard now at `PASS`, this prep-exit blocker is closed

### AQ-PREP-010 Keep the quality dashboard refreshed automatically

- Status: Done
- Why:
  The dashboard is now important enough to influence prep-gate decisions, so stale snapshots are no longer just a convenience issue; they risk making human-facing status and queue wording drift away from current gate truth.
- Evidence:
  - `docs/current/QUALITY_DASHBOARD.md`
  - `sed -n '1,220p' \"$CODEX_HOME/automations/xbrainlab-executor/automation.toml\"`
  - `automation_update mode=update id=xbrainlab-executor`
- Result:
  - the existing executor automation now includes an explicit fast-dashboard refresh path using `/home/administrator/.local/bin/poetry run python scripts/dev/update_quality_dashboard.py --skip-if-fresh-minutes 60` when `AQ-PREP-010` is top eligible
  - the freshness guard is now documented and wired into the recurring unattended path instead of being only a manual command hidden in docs
  - prep-gate recordkeeping now explicitly treats direct reruns as authoritative when a saved dashboard artifact drifts out of date
  - the latest fast dashboard refresh is now aligned with current workspace-safe commands and reports `PASS`; after the `AQ-006` local-first shell change, the approved `ai-assistant-open.png` reference has also been re-promoted so the automation path is again suitable as a human-facing health snapshot instead of failing on stale Gemini-era baseline drift

## Recently Completed

### AQ-PREP-001 Fix black screenshot baseline output

- Status: Done
- Result:
  the capture helper now grabs the rendered Qt main window directly instead of relying on a black-prone virtual-display screenshot path
- Evidence:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - artifact: `artifacts/ui/main-window-initial.png`

## Repair Queue

Repair Loop current queue is complete. No active repair items remain.

### AQ-001 Strengthen dataset import and label import reliability

- Status: Done
- Why:
  Dataset import remains the highest-value repair surface once the prep gate is cleared.
- Current focus:
  - keep the real GDF duplicate-channel ambiguity visible all the way through import, dataset summary, and preprocess-time guardrails instead of leaving it trapped in import internals
  - avoid higher-risk normalization behavior until there is stronger evidence that observability plus guardrails are still insufficient
- Evidence:
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/controller/test_dataset_controller.py -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/controller/test_preprocess_controller.py -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/tools/real/test_real_tools.py -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw.py -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw_data_loader.py -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/pipeline/test_all_real_tools.py::TestAllRealTools::test_channel_selection_tool tests/integration/pipeline/test_all_real_tools.py::TestAllRealTools::test_set_montage_tool -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
- Result:
  - this repair closure was recorded during the earlier repair-loop attempt, but the `2026-04-19` prep recheck revoked that phase transition; `AQ-001` remains completed work without re-opening the repair queue on its own
  - real GDF duplicate-channel ambiguity now survives import as structured `Raw` runtime detail under `gdf_duplicate_channel_names`, and the same signal is now aggregated into both dataset-level and preprocess-level diagnostics
  - `BackendFacade.get_data_summary()` now exposes `runtime_signals`, `gdf_duplicate_channel_files`, and `gdf_duplicate_channel_details`, so higher-level callers no longer need to inspect individual `Raw` objects directly
  - `PreprocessController.get_runtime_diagnostics()` and `BackendFacade.get_preprocess_diagnostics()` now keep the same ambiguity visible after channel-sensitive operations begin
  - `RealGetDatasetInfoTool` now surfaces the GDF duplicate-channel ambiguity in its returned dataset summary instead of hiding it behind a generic "load succeeded" path
  - channel-sensitive real preprocess paths now append an explicit guardrail note for the ambiguity instead of silently proceeding through channel selection, re-reference, montage confirmation, or standard preprocess
  - the real-data IO slice remains green at `31 passed, 13 warnings`, and the targeted real-data preprocess guardrail slice passed at `2 passed, 2 warnings`, so this closure did not regress supported-format imports
  - `AQ-001` now closes without immediate normalization; the underlying channel-identity ambiguity remains tracked under `BUG-DATASET-007`, but the next repair step can move to downstream preprocess readiness instead of staying stuck on import-side observability

### AQ-002 Improve preprocess readiness and downstream state propagation

- Status: Done
- Why:
  Preprocess state drives training readiness and downstream workflow coherence.
- Current focus:
  - keep downstream training, evaluation, and visualization surfaces honest when preprocess invalidates epoch/dataset state
  - close the remaining symmetric UI propagation gap before moving on to training-state sync
- Evidence:
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/controller/test_preprocess_controller.py -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q`
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... preprocess_changed -> TrainingPanel ... PY`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q`
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... preprocess_changed -> EvaluationPanel ... PY`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q`
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... preprocess_changed -> VisualizationPanel ... PY`
- Result:
  - the controller/facade baseline stayed green at AQ-002 kickoff (`10 passed` and `39 passed`), which made it possible to isolate the first real downstream drift instead of re-proving AQ-001's import-side guardrails
  - that first drift is now fixed under `BUG-TRAINING-002`: `TrainingPanel` had been listening only to dataset events, so a `preprocess_changed` invalidation could leave the `Start Training` button enabled until a page switch or manual refresh
  - `TrainingPanel` now subscribes to `preprocess_changed`, the focused readiness regression slice passes at `7 passed`, the shared event-bridge slice now passes at `7 passed`, and the direct offscreen repro now flips the button from `initial True Start Training` to `after_notify False Please configure: Data Splitting`
  - the second drift is now fixed under `BUG-EVAL-001`: `EvaluationPanel` had been listening only to `training_stopped`, so preprocess invalidation could leave stale fold/run selections visible until a manual refresh
  - `EvaluationPanel` now subscribes to `preprocess_changed`, the focused regression slice passes at `3 passed`, and the direct offscreen repro now flips the panel from `initial 1 Fold 1: Plan A` to `after_notify 1 No Data Available 0`
  - the third drift is now fixed under `BUG-VIZ-001`: `VisualizationPanel` had been listening only to `training_stopped`, and its combo refresh path also failed to clear stale plan/run entries when trainers disappeared
  - `VisualizationPanel` now subscribes to `preprocess_changed`, `refresh_combos()` clears stale selections when no trainers remain, the focused coverage slice passes at `17 passed`, and the direct offscreen repro now flips the panel from `initial 2 Fold 1 (EEGNet) 2` to `after_notify 1 Select a plan 0`
  - with the controller/facade baseline still green and the three symmetric downstream UI propagation drifts now fixed, AQ-002 can close and the queue can move on to `AQ-003`

### AQ-003 Stabilize training state synchronization

- Status: Done
- Why:
  Training events fan out into logs, plots, evaluation, and visualization.
- Current focus:
  - close the remaining `training_updated`-era gaps inside the training panel itself, then retire AQ-003 only after live progress, selection, and stale-log semantics are all covered
- Evidence:
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
- Result:
  - downstream result-surface fanout is now covered under `BUG-EVAL-002/003` and `BUG-VIZ-002/003`: evaluation and visualization clear stale selections immediately on `history_cleared` and `config_changed`
  - training-panel sync is now covered under `BUG-TRAINING-003/004/005/006/007`: immediate active-run population, trainer-invalidating clears, stale-selection replacement, auto-follow vs manual pin semantics, and stale log clearing on history/config resets
  - `training_updated` live progress and plot refresh now have direct focused coverage, with the latest slice confirming history-table progress `1/5 -> 2/5` and plot epochs `[1] -> [1, 2]` without waiting for a delayed page switch
  - with focused slices green at `16 passed`, `5 passed`, `19 passed`, and `11 passed`, plus the shared UI sweep green at `769 passed, 12 skipped, 1 warning`, no further AQ-003 training-state sync drift is currently reproduced

### AQ-004 Tighten evaluation consistency

- Status: Done
- Why:
  Evaluation depends on cross-screen state alignment after training completes.
- Current focus:
  - preserve the analyst's current fold/run context across harmless refreshes instead of bouncing back to the first plan whenever training completion triggers `update_panel()`
- Evidence:
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... EvaluationPanel preserve Fold 2 / Average across training_stopped ... PY`
- Result:
  - `BUG-EVAL-004` is now fixed: `EvaluationPanel.update_panel()` preserves the selected plan and run when they are still valid, instead of resetting to `Fold 1 / Repeat 1` on `training_stopped`
  - the preservation logic now follows stable plan identity or label plus stable run identity or label, so both `Average (Finished Runs)` and a specific repeat survive a harmless completion refresh
  - the latest direct repro now stays on `before Fold 2: Plan B Average (Finished Runs)` -> `after Fold 2: Plan B Average (Finished Runs)` instead of snapping back to the first plan
  - with focused evaluation coverage green at `7 passed`, the bridge slice still green at `11 passed`, and the shared UI sweep green at `771 passed, 12 skipped, 1 warning`, no further AQ-004 evaluation-consistency drift is currently reproduced

### AQ-005 Stabilize visualization validation and runtime behavior

- Status: Done
- Why:
  Visualization remains the highest-risk user-facing area once core flows are stable.
- Current focus:
  - preserve valid plan/run context across harmless refreshes instead of snapping back to the first trainer whenever training completion triggers a panel refresh
  - replace the stale skipped redesign suite with a headless-safe current-architecture regression slice so visualization validation is no longer hidden behind an outdated class-level skip
- Evidence:
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
- Result:
  - `BUG-VIZ-004` is now fixed: `VisualizationPanel` preserves the selected plan and run when they are still valid, instead of resetting to the first trainer on harmless refreshes like `training_stopped`
  - the preservation logic now follows stable plan identity or label plus stable run identity or label, so average-mode analysis can survive completion refresh without bouncing back to the first plan
  - `BUG-ENV-001` is now fixed: the old skipped `test_visualization_panel_redesign.py` surface has been replaced with a headless-safe current-architecture regression suite that runs green at `6 passed` instead of hiding coverage behind class-level skip and stale harness drift
  - the latest focused visualization slices are green at `20 passed` and `6 passed`, and the shared UI sweep is now green at `782 passed, 3 skipped, 1 warning`; the remaining three skips live in other files and no longer belong to this visualization redesign debt

### AQ-006 Remove or demote remote API dependencies from user-facing flows

- Status: Done
- Why:
  The longer-term target remains local-model-first operation rather than OpenAI/Gemini dependency.
- Current focus:
  - make user-facing AI shell controls fail closed when local-only assumptions are violated instead of silently switching the product into a remote mode
  - keep remote Gemini affordances explicitly secondary and clearly labeled when they are available at all
- Evidence:
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_ui_misc.py -q`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
- Result:
  - `BUG-AGENT-002` is now fixed: deleting an active local model no longer silently switches the assistant to Gemini; `AgentManager.prepare_model_deletion()` now blocks that path and `ModelSettingsDialog` respects the failed precondition instead of removing the model anyway
  - the chat model menu is now local-first and more honest: `Local` stays primary, Gemini only appears when explicitly enabled, and any remote option is labeled `Gemini (Remote)` instead of presenting remote fallback as the default surface
  - `BUG-AGENT-001` is now narrower: the remaining local-assistant blocker is missing local model cache plus dedicated bootstrap validation, not user-facing silent remote fallback
  - the focused AQ-006 assistant slices are green at `191 passed`, and the shared UI sweep remains green at `782 passed, 3 skipped, 1 warning`

## Deferred

### DQ-001 Broad UI redesign

- Status: Deferred
- Reason:
  The user wants intentional design changes discussed first.

### DQ-002 Large architecture rewrite outside backend/test-infra stabilization

- Status: Deferred
- Reason:
  More runtime evidence is needed before choosing broad restructuring.
