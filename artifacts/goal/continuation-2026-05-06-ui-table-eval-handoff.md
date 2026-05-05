# XBrainLab Product Completion Continuation - 2026-05-06 UI Table / Eval Gate

Use this as the next-run handoff for the active product-completion goal. Do not
mark Goal 1 product-complete while the blockers below remain.

## Current Repo / Branch

- Repo: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
- Branch: `codex/stabilization-autopilot`
- Do not push.
- Do not touch / stage / revert `.vscode/settings.json`, root `settings.json`, or the user-added
  `.agents/skills/*` changes unless the user explicitly asks.

Expected dirty files after this handoff:

```text
 M .agents/skills/README.md
 M .vscode/settings.json
 M settings.json
?? .agents/skills/clean-code-reviewer/
?? .agents/skills/data-interpretation-reviewer/
?? .agents/skills/mcp-adapter-reviewer/
?? .agents/skills/performance-resource-reviewer/
?? .agents/skills/release-packaging-reviewer/
?? .agents/skills/security-privacy-reviewer/
?? .agents/skills/thesis-evidence-reviewer/
?? .agents/skills/ui-product-reviewer/
```

## Latest Validated Commits

```text
d5388e7 test: guard capability-gated controller readiness
57b5d9c docs: refresh handoff after train gate audit
82576f5 ui: prefer train capability over stale controller
bb57beb ui: use backend truth for split replacement
```

## What Was Closed In This Slice

- Data Interpretation wizard selector visible text:
  - label carrier selectors show user-facing labels such as `Trial type` / `Onset`.
  - backend recipe choices still preserve raw values such as `trial_type`.
- Review Summary contrast:
  - alternate row color lowered to `#232323`, avoiding harsh black/white striping.
- Label/Event review table readability:
  - label-carrier `Format` column widened so `BIDS events` remains visible in product-width dialog.
- Dataset loaded table artifact:
  - `artifacts/ui/data-interpretation-applied.png` shows loaded rows filling to the sidebar.
  - `Labels (4)` is muted text, not success-green.
- Automated geometry guard:
  - `table_state()` now records `widget_width`, `panel_width`, `table_right_x`,
    `right_boundary_x`, and `right_gap_to_boundary`.
  - `build_table_geometry_review()` now fails if a table fills only its own viewport but leaves a
    visible gap before the content boundary.
  - Latest `artifacts/ui/data-interpretation-replay.json` records
    `widget_width=1020`, `table_right_x=1020`, `right_boundary_x=1020`,
    `right_gap_to_boundary=0` for the 1280px loaded Dataset capture.
- Visualization sidebar `Set Montage` missing-result handling:
  - no longer silently returns when `execute_application_command()` unexpectedly returns `None`.
  - mock / legacy contexts use `run_legacy_controller_fallback()`; real `Study` contexts refuse
    controller fallback.
- Dataset file import boundary:
  - if `scan_source` capability exists but Data Interpretation command sequencing is unavailable,
    the UI shows `Interpretation unavailable`.
  - it does not fall through to `LoadDataCommand` or `DatasetController.import_files()`.
- Training model selection command truth:
  - service-success path now trusts `ConfigureTrainingCommand` and the selected model holder.
  - it no longer re-reads stale `TrainingController.get_model_holder()` before showing success.
  - architecture compliance now guards this controller echo pattern.
- Training split replacement command truth:
  - real `Study` path uses backend `generate_dataset` / `clear_datasets` capability truth to decide
    whether existing generated datasets / trainer must be cleared before a new split.
  - stale `TrainingController.has_datasets()` / `get_trainer()` no longer skips confirmation and
    `ClearDatasetsCommand`.
- Start Training command truth:
  - real command-capable path uses backend `train` capability truth to decide whether to dispatch
    `TrainCommand`.
  - stale `TrainingController.is_training()` no longer silently skips an enabled backend train
    command.
- Capability-gated readiness architecture guard:
  - `tests/architecture_compliance.py` now flags `controller.is_training()`,
    `controller.has_datasets()`, and `controller.get_trainer()` in command paths that already have
    backend capability truth.
  - Such reads must live in explicit `capability is None` legacy branches.

## Validation Already Run

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_data_interpretation_replay.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_table_columns_fill_available_width \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_refits_table_after_loaded_rows_settle \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_events_column_uses_semantic_text_and_muted_color \
  -q
# 23 passed

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py
# exit 0

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
# exit 0; walkthrough status passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run mkdocs build --strict
poetry run python tests/architecture_compliance.py
# all passed; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_real_study_montage_refuses_controller_fallback \
  tests/unit/ui/test_refresh_coordinator.py \
  tests/unit/ui/test_panel_event_bridges.py \
  -q
# 46 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  tests/unit/ui/dataset/test_panel.py \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  -q
# 89 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  tests/unit/ui/training/test_training_panel.py \
  -q
# 50 passed

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 23 passed
```

No local LLM eval was run for these UI / architecture guard slices.

## Tool-Call Eval Gate Policy

Do not run full primary/fallback x3 local eval for routine changes.

- Fast dev gate:
  - deterministic eval
  - changed / failed cases only
  - repeat `1`
  - no fallback model
- Candidate gate:
  - primary model only
  - affected case families
  - repeat `1` or `2`
- Release / thesis gate:
  - deterministic full suite
  - primary full suite x3
  - fallback full suite x3
  - dashboard refresh
  - record disk / cache / `nvidia-smi` VRAM used/free, latency, and resource pressure

RTX 5070 Ti 16GB has already shown near-full VRAM pressure on fallback x3. If VRAM is nearly full,
do not start a full fallback x3 run. Use deterministic changed cases or primary subset unless the
work is explicitly a release / thesis evidence gate.

## Still Cannot Claim Product Complete

- UI refresh remains partially mixed:
  - command-result coordinator baseline exists, but observer/manual/tab-switch/event-specific
    refreshes still remain.
- Product runtime controller fallback is still an audit target:
  - controller fallback must stay explicit mock / unit-test / legacy-only, not silent product
    runtime mutation.
- Data Interpretation is stronger but not final:
  - embedded label editor, raw trigger selector, complex GDF/MAT anchor reconciliation, XDF/LSL full
    parser, full real-data manual certification, and recipe diff/review UX remain.
- Human desktop acceptance remains open:
  - Windows launcher click-through, dual monitor / DPI, and long real local-model desktop session
    are not verified.
- Agent / MCP release depth remains open:
  - long autonomous ChatPanel workflow, UI-routing render, full recovery behavior, HTTP MCP
    transport, and long-running MCP job progress/cancel/recovery remain.
- Tool-call benchmark evidence must not be used as UI / launcher / import wizard product evidence.

## Suggested Next Slices

1. Continue `UI Command Refresh Coordinator + Controller Fallback Audit`.
   - Audit remaining `result is None` branches and controller read echoes.
   - Keep product runtime mutations on ApplicationService, with controller fallback only in explicit
     mock / legacy branches.
   - Continue routing post-command refresh through the coordinator.
2. Continue Data Interpretation wizard maturity.
   - Add a small recipe diff/review UX slice or a safer label-carrier edit slice with screenshot
     artifact.
3. Only after product/UI/backend path stabilizes, refresh affected tool-call eval cases using the
   fast/candidate gate. Reserve full primary/fallback x3 for release/thesis evidence.
