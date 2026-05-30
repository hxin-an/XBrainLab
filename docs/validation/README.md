# XBrainLab 驗證策略

最後更新：`2026-05-30`

這頁說明 evidence 能證明什麼，也說明不能證明什麼。

## 原則

不要把一種 evidence 放大成所有 claim。

| Evidence | 能支撐 | 不能支撐 |
| --- | --- | --- |
| CI green | branch 基本可 review，跨平台測試目前通過。 | product complete、human desktop acceptance。 |
| `mkdocs build --strict` | 文件站可建。 | 文件內容一定正確。 |
| architecture guard | 沒有已知 forbidden path regression。 | 所有 runtime flow 都已人工驗收。 |
| backend focused tests | command / state / result contract。 | UI 使用者體驗完整。 |
| automated UI walkthrough | 可觀察 UI baseline、截圖、按鈕狀態。 | 人手 Windows acceptance、DPI / dual-monitor、長時間 local model session。 |
| human-observable product smoke | 代表性使用者流程的視窗可見性、primary action 可見性、selected/applied scope、無 crash。 | 完整 release approval、所有資料格式與長時間模型 session。 |
| tool-call eval | tool selection / parameter / state transition 的 benchmark slice。 | EEG training quality、UI completion、產品完成。 |
| MCP walkthrough | adapter baseline、tools/list、tools/call、HTTP / stdio path。 | full client certification、remote production security。 |
| launcher smoke | launcher / startup baseline。 | signed installer、release approval。 |

## MVP Gate

| Phase | 需要的最低 evidence |
| --- | --- |
| 1A Backend Cleanup | architecture guard、focused command tests、UI refresh tests。 |
| 1A-V Validation Reality Gap | test matrix、現有 artifacts claim audit、launcher -> Data Interpretation preview -> apply 的 product smoke。 |
| 1B Data Interpretation | scan / preview / validate / apply tests，加 representative format artifact。 |
| 1C Tool-Call Baseline | agent tool tests、MCP adapter tests、blocked reason / structured result checks。 |
| 1D Desktop Acceptance | human Windows click-through notes，加 automated walkthrough screenshot evidence。 |

## Artifact 解讀

`artifacts/` 是機器產物和 evidence，不是 current truth。

current truth 以這些文件為準：

- [current.md](../current.md)
- [planning/roadmap.md](../planning/roadmap.md)
- [architecture/README.md](../architecture/README.md)
- [validation/README.md](README.md)

## 2026-05-30 Release-Candidate Gate Follow-Up

Manual-test gating on `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual`
treated non-blocking findings as work to clear, not as deferred polish. The current
branch fixed and validated these product-quality gaps:

- saliency 2D map / topomap / spectrogram rendering now keeps Qt/Matplotlib
  figure creation on the UI thread, avoiding native Qt backend crashes from
  background-thread figure creation while still showing visible render / error
  states;
- metrics and model-selection tables use dark active/inactive/disabled palettes and
  clear initial selection, preventing white selected rows from hiding text;
- data-splitting and epoching dialogs now have current screenshot evidence with
  dark readable controls and visible primary actions;
- stale current-tree `human-like-walkthrough` and `audit-visualization-render`
  artifacts were removed; historical records can still mention them, but current
  evidence now points to `data-import-wizard-steps`, `app-polish`, and
  `visualization-render`;
- training record figure helpers use figure-scoped rendering and close empty
  figures, preventing matplotlib figure accumulation during repeated visualization;
- `ApplicationService` lazy service wrappers now expose explicit command handlers
  instead of generic `__getattr__` forwarding;
- UI-only `GenerateDatasetCommand.generator` is hidden from automation / MCP schemas
  and rejected when supplied through automation payloads;
- Dataset import UI tests were updated to the `ReviewInterpretationCommand` command
  path, so the focused UI suite no longer protects the old scan/preview/validate
  sequence as the product behavior;
- evaluation and visualization approved UI baselines were refreshed after product
  review of the intentional no-data and wrapped-control layouts.

Validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/update_quality_dashboard.py
# Overall status: PASS
# generated_at: 2026-05-30 18:10:25 UTC+08:00
# commit: 53bed8b96623
# workspace: /mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual
# checks: Ruff, Basedpyright, Architecture Compliance, Startup Smoke,
# UI Baseline Capture, UI Dialog Acceptance, UI Product Walkthrough,
# UI Unit Suite, Real-Data IO Integration all PASS

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_epoching_dialog.py
# PASS; refreshed artifacts/ui/epoching-dialog/

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_ui_polish_surfaces.py
# PASS; refreshed artifacts/ui/app-polish/

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/run_tests.py ui
# 1242 passed

poetry run basedpyright
# 0 errors, 0 warnings, 0 notes

poetry run mkdocs build --strict
# PASS

poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q
# 2 passed

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_windows_launcher_walkthrough.py
# status: passed
```

This supports the branch as a stronger release-candidate preflight. It still does
not claim signed packaging, full human Windows click-through acceptance, arbitrary
BIDS validator compliance, or scientific model-quality conclusions.

## 2026-05-25 Mainstream EEG/BCI Format Gate

Mainstream format coverage was rechecked with checked-in compact fixtures plus
local-only public fixtures under `tests/fixtures/data/public/`. The public fixture
cache is intentionally ignored by git; `scripts/dev/fetch_public_eeg_fixtures.py`
downloads it and now verifies SHA-256 for downloaded files. Current
small representatives cover:

- checked-in GDF + MAT labels: BCI Competition IV 2a style `A01T/A02T/A03T`;
- checked-in compact multiformat derivatives: FIF, FIF.GZ, EDF, BDF, BrainVision,
  EEGLAB SET, and epoched FIF;
- public local-only fixtures: PhysioNet EDF, BBCI GDF, SCCN EEGLAB SET, MNE CNT,
  MNE BrainVision;
- downloaded local-only MNE-BIDS tiny EEG root with BrainVision data,
  `events.tsv`, `events.json`, `channels.tsv`, participants, sessions, scans,
  and electrode sidecars;
- scan/preview validation matrix entries for CSV, TSV, TXT, MAT, BIDS events,
  and explicitly blocked XDF/LSL.

The gate found one product issue: a generic `trial/class` TSV could be interpreted
as if `trial` were an EEG event code. Event-order placement now defaults that case
to `trial order` and asks the user to choose target EEG events instead of blocking
on a nonexistent event called `trial`.

Validation:

```bash
poetry run python scripts/dev/fetch_public_eeg_fixtures.py
# downloaded/validated public fixtures, including mne-bids-tiny-eeg

poetry run python scripts/dev/report_data_interpretation_format_matrix.py --format json
# all_expected_capabilities_observed: true
# all_expected_capabilities_match: true

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/io/test_io_integration.py \
  tests/integration/io/test_public_bids_fixture.py \
  tests/integration/pipeline/test_public_cross_source_training_smoke.py -q
# 36 passed

poetry run python scripts/dev/run_public_cross_source_training_smoke.py \
  --format json --strict
# 4 passed, 0 missing, 0 failed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/integration -q
# 215 passed

poetry run ruff check .
# PASS

poetry run basedpyright scripts/dev/fetch_public_eeg_fixtures.py \
  scripts/dev/report_data_interpretation_format_matrix.py \
  scripts/dev/report_dataset_validation_matrix.py \
  scripts/dev/run_public_cross_source_training_smoke.py \
  tests/unit/scripts/test_fetch_public_eeg_fixtures.py \
  tests/unit/scripts/test_report_data_interpretation_format_matrix.py \
  tests/unit/scripts/test_report_dataset_validation_matrix.py \
  tests/unit/scripts/test_run_public_cross_source_training_smoke.py \
  tests/integration/io/test_public_bids_fixture.py
# 0 errors, 0 warnings, 0 notes

poetry run mkdocs build --strict
# PASS

poetry run python tests/architecture_compliance.py
# Architecture compliant

poetry run python scripts/dev/update_quality_dashboard.py
# Overall status: PASS
```

This supports mainstream tier-1/tier-2 import breadth for the formats above. It
does not claim full BIDS validator compliance, XDF/LSL support, or scientific
replication quality for arbitrary public datasets.

## 2026-05-25 Manual-Test Audit Follow-Up

Manual testing exposed multiple issues that older automated evidence did not catch.
The follow-up audit found and fixed two validation gaps:

- Product walkthrough mocks and visualization capture scripts still confirmed Data
  Interpretation without choosing the new supervised label source. They now select
  internal EEG events when using synthetic internal labels, and visualization capture
  starts tiny training with an explicit confirmation boundary.
- BIDS scan had let `participants.tsv` / `*_channels.tsv` appear as label/event
  carriers. BIDS metadata tables are now reported as metadata context, while
  `events.tsv` remains the label/event carrier. Saved import recipes now preserve
  the BIDS summary used by epoch handoff and recipe reload review.

Focused validation from `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual`:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/ui \
  tests/unit/scripts/test_capture_data_interpretation_replay.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/unit/scripts/test_capture_visualization_render_walkthrough.py \
  tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py -q
# 100 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_data_interpretation_scan.py \
  tests/unit/backend/application/test_data_interpretation_candidate.py \
  tests/unit/backend/application/test_data_interpretation_label_carriers.py \
  tests/unit/backend/application/test_data_interpretation_service.py \
  tests/unit/backend/application/test_data_interpretation_review.py \
  tests/unit/backend/application/test_data_interpretation_recipe.py \
  tests/unit/backend/application/test_data_interpretation_formats.py \
  tests/integration/backend/test_application_service_workflow.py -q
# 80 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/integration/ui/test_dialog_acceptance.py \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_redesign.py -q
# 106 passed

QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true poetry run python \
  scripts/dev/capture_visualization_render_walkthrough.py \
  --output-dir artifacts/ui/visualization-render --timeout-seconds 540
# passed; 3 rendered saliency tabs and 3D blocked-state evidence captured

poetry run python scripts/dev/update_quality_dashboard.py
# Overall status: PASS

poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q
# 21 passed, 10 skipped

poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q
# 2 passed
```

This supports the integrated manual-test branch as a stronger automated preflight.
It still does not replace human Windows click-through acceptance.

## 2026-05-25 Subagent-Gated Data Import Closure

Subagent gates for Data Import, runtime UI, backend state, and test completeness
were treated as blockers. Several worker findings were stale on the current branch,
but Gate A exposed three live Data Import issues:

- ordinary folders containing `sub-*` EEG filenames could be misclassified as BIDS;
- Review and Import could split one missing `events.tsv` problem into multiple
  action items and route label-source issues to the wrong step;
- Smart Parse metadata only applied subject/session even though Review Metadata
  exposes subject/session/task/run.

The current branch now requires a stronger BIDS folder shape before auto-classifying
a folder as BIDS, canonicalizes missing `events.tsv` warnings into one Load Labels
action item, and preserves Smart Parse subject/session/task/run in the Data Import
metadata override recipe while keeping legacy subject/session consumers compatible.

Focused and broad validation after the gate fixes:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_data_interpretation_scan.py \
  tests/unit/backend/application/test_data_interpretation_candidate.py \
  tests/unit/backend/application/test_data_interpretation_review.py \
  tests/unit/backend/application/test_data_table_service.py \
  tests/unit/backend/controller/test_dataset_controller.py \
  tests/unit/ui/dataset/test_smart_parser.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q
# 158 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/integration -q
# 200 passed, 14 skipped

poetry run python scripts/dev/update_quality_dashboard.py
# Overall status: PASS

poetry run ruff check .
# PASS

poetry run basedpyright XBrainLab/backend/application/data_interpretation_scan.py \
  XBrainLab/backend/application/data_interpretation_candidate.py \
  XBrainLab/backend/application/data_interpretation_review.py \
  XBrainLab/backend/application/data_table_service.py \
  XBrainLab/backend/controller/dataset_controller.py \
  XBrainLab/ui/dialogs/dataset/smart_parser_dialog.py \
  XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py
# 0 errors, 0 warnings, 0 notes

poetry run mkdocs build --strict
# PASS

poetry run python tests/architecture_compliance.py
# Architecture compliant
```

The skipped integration cases are public EEG fixtures that are not downloaded in
this workspace. This gate supports the branch as a stronger manual-test candidate;
it still does not prove arbitrary BIDS coverage or replace Windows human
click-through acceptance.

## 2026-05-25 Gate E Test-Coverage Follow-Up

Gate E reviewed integration-test completeness and failed the branch as originally
gated: backend command tests were strong, but product-visible Data Import and
wizard state still had too much mock-heavy coverage. Two regressions were then
made reproducible and fixed:

- Loading an external label folder from the Load Labels step could refresh the
  carrier list but leave Match Labels in `Labels inside EEG files` mode. A new UI
  integration test uses real `ApplicationService` scan / preview / validate plus
  the real wizard rescan handler and asserts Match Labels switches to loaded
  label files.
- Epoch dialog event selection had regressed after checked-event support: normal
  selection-only dialogs could no longer accept a selected event, while import
  handoff dialogs still must reject stale selection when all recommended events
  are unchecked.

The fast quality dashboard now includes `UI Product Walkthrough`, which runs the
existing product walkthrough plus the real Data Import wizard runtime regression.

Focused validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/ui/test_product_walkthrough.py \
  tests/integration/ui/test_data_import_wizard_runtime.py -q
# 5 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/ui/test_dialog_acceptance.py::test_epoching_dialog_accepts_selected_event_and_baseline_toggle \
  tests/unit/ui/components/test_dialogs.py::test_epoching_dialog_init \
  tests/unit/ui/test_dialogs_extra.py::TestEpochingDialog::test_import_handoff_uses_checked_events_not_stale_selection -q
# 3 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application \
  tests/integration/backend/test_application_service_workflow.py -q
# 209 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_visualization_render_walkthrough.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_dialogs_extra.py -q
# 132 passed

QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true poetry run python \
  scripts/dev/capture_visualization_render_walkthrough.py \
  --output-dir artifacts/ui/visualization-render --timeout-seconds 540
# passed

poetry run python scripts/dev/update_quality_dashboard.py
# Overall status: PASS
```

Remaining coverage boundary: public cross-source fixtures are still optional /
skipped when absent. PhysioNet EDF, BBCI GDF, and SCCN EEGLAB are training-smoke
fixtures when present; the compact MNE CNT fixture is IO/preprocess/epoch-only
because it has too few usable epochs for a class-balanced training split. The
default dashboard still does not claim human Windows click-through acceptance or
full local-LLM runtime acceptance.

## 2026-05-22 Epoch Dialog Label Transparency

Manual UI review found that Epoch dialog text labels could render with visible
label-background blocks on some Qt/desktop themes because the dialog and shared
dialog info/warning label styles did not set transparent label backgrounds. Epoch
dialog label rules and shared dialog info/warning label styles now explicitly use
`background-color: transparent`.

Focused validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_dialogs_extra.py \
  tests/unit/ui/components/test_dialogs.py \
  tests/unit/ui/dialogs/test_dialogs_structure.py \
  tests/unit/ui/preprocess/test_preprocess_panel.py -q
# 74 passed

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/run_tests.py ui
# 1161 passed
```

## 2026-05-21 Load Labels Restore Regression

Manual testing found that removing a label file in Load Labels and loading it back
could leave Match Labels stale: the Load Labels page showed the source, while Match
Labels still filtered the carrier as removed. The fix restores excluded carriers
when the same known label file or folder is loaded again, refreshes the Match Labels
state, and returns the wizard to the outer scan loop before entering Match Labels
when a brand-new label source requires rescanning.

A follow-up manual test found that removing one label file from an already-loaded
label folder, then loading the same file back, could show the carrier twice because
the file was also added as a second source. The restore path now treats files already
covered by a loaded folder as the same source: it restores the carrier but does not
add a duplicate file-level label source.

Another manual test found the same visual duplicate when the loaded source itself was
the exact label file: Load Labels rendered both the carrier row and the loaded file
source row. The UI now collapses an exact file source when a visible carrier row has
the same normalized path, while keeping loaded folder sources visible as the source
scope.

Another follow-up found that a loaded folder rendered file rows and the folder-scope
row with identical `Remove` buttons, making single-file removal indistinguishable
from unloading the whole folder. File carrier rows now use `Remove file`, while the
folder source is shown as a separate source bar with `Remove all from this folder`.
Regression coverage verifies that removing one file from a loaded folder leaves
sibling label files and the loaded folder source intact.

A folder named `label` also looked like another label file when its basename was used
as the row title. Loaded folder sources now render as `Label source: ...` above the
file list, so the list itself contains only actual label files. Cleanup also detaches
old source-row widgets from the dialog tree before `deleteLater()`, preventing stale
hidden remove buttons from being picked up after remove -> reload cycles.

The same validation pass exposed a reproducible UI-suite crash in the preprocessing
preview: `PlotWidget.clear()` deleted persistent PyQtGraph crosshair/title items and
later resize events touched deleted Qt objects. Preprocess preview clearing now removes
transient plot data only and keeps persistent crosshair items alive.

Focused validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_ui_misc.py \
  tests/unit/ui/dialogs/test_preview_widget.py \
  tests/unit/ui/preprocess/test_preprocess_plotter.py \
  tests/unit/ui/preprocess/test_preprocess_panel.py -q
# 273 passed

poetry run python scripts/dev/run_tests.py ui
# 1160 passed

poetry run ruff check \
  XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py \
  XBrainLab/ui/panels/preprocess/preview_widget.py \
  XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/dialogs/test_preview_widget.py \
  tests/unit/ui/preprocess/test_preprocess_plotter.py
# All checks passed!

poetry run basedpyright
# 0 errors, 0 warnings, 0 notes
```

## 2026-05-16 Manual-Test Integration Preflight

Manual-test branch `integrate/all-branches-manual-test` was refreshed after a
multi-agent read-only audit found capability, label-placement, MCP, and UI status
risks. The follow-up patch fixed preprocessing-aware raw-load blockers, destructive
command confirmation metadata, event-code versus timestamp label placement, internal
EEG label choice persistence, conversion-fallback pairing status, MCP HTTP conflict
confirmation metadata, and dashboard typecheck failures.

Validation run from `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual`:

- `poetry run python scripts/dev/update_quality_dashboard.py`: `PASS`.
- `poetry run ruff check .`: `PASS`.
- `poetry run basedpyright`: `PASS`.
- `poetry run mkdocs build --strict`: `PASS`.
- `poetry run python tests/architecture_compliance.py`: `PASS`.
- Data Import / Epoch / UI focused suite: `178 passed`.
- ApplicationService / automation / agent surface suite: `153 passed`.
- MCP unit and integration suite: `18 passed`.
- `poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`:
  `21 passed, 10 skipped` because optional public fixtures are not present.
- Pipeline smoke:
  `tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics`
  and
  `tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet`:
  `2 passed`.

This supports a runnable automated preflight for hand testing. It still does not
prove human Windows click-through acceptance, full BIDS validation, every public EEG
format fixture, or final UI approval for Match Labels / Review and Import.

## 2026-05-14 Artifact Live-Capture Deduplication Checkpoint

Artifact hygiene removed tracked top-level `artifacts/ui/*.png` live-capture files that duplicated
approved `tests/baselines/ui/` references byte-for-byte and made future top-level dashboard captures
local-only through `artifacts/ui/.gitignore`. Current UI walkthrough evidence remains in named
`artifacts/ui/*/` subdirectories, while approved regression references remain in
`tests/baselines/ui/`.

Focused validation from that slice covered dashboard markdown / UI baseline helper tests, strict
docs build, architecture compliance, and whitespace checks. This supports artifact retention hygiene;
it does not prove visual freshness, runtime correctness, or human desktop acceptance.

## 2026-05-14 Agent Confirmation Boundary Payload Evidence Checkpoint

Agent confirmation payloads now include a `decision_boundary` field so UI clients can distinguish
ordinary tool confirmation from backend semantic-apply confirmation. The focused controller test
asserts both the default `tool_confirmation` path and `semantic_apply` for Data Interpretation apply.
This supports clearer agent/UI confirmation behavior; it does not prove full agent tool-call quality.

## Reality-Gap Audit

當 human walkthrough 發現 dashboard / automated smoke 沒抓到的問題時，不能只修單點 bug。
必須反向更新 validation strategy：

- 記錄是哪一種 evidence 漏掉問題。
- 補一個能重跑的 test、walkthrough artifact 或 product smoke。
- 明確區分 backend truth、UI presentation truth、human-observable truth。
- 對 launcher / desktop 問題，至少記錄 Qt platform、screen geometry、window geometry、exit code。

目前需要補強的代表性 smoke：

```text
launcher
-> main window visible on current screen
-> Import file / Import folder
-> Load label folder from a different location
-> Review Metadata
-> Match Labels
-> Review and Import
-> preview shows selected scope separately from scan location
-> primary Import / Apply action remains visible
-> apply loads exactly selected EEG files and loaded label carriers
```

2026-05-10 automated coverage now includes focused backend tests for external `label_sources`,
selected scope vs scan location, structured action items, dialog primary-action visibility,
left-side Cancel / right-side wizard navigation behavior, no nested table scroll regression,
one-panel-per-step wizard navigation, task-panel layout checks, Dataset sidebar first-layer action
cleanup, and a product-flow unit smoke for import -> load label folder -> review metadata ->
match labels -> review/import. Updated offscreen screenshots live under
`artifacts/ui/data-import-wizard-steps/`. This is not a replacement for human Windows desktop
acceptance or a full BIDS support claim.

2026-05-11 follow-up coverage adds the final first-version Match Labels source model:
`Labels inside EEG files` hides loaded-label pairing, while `Loaded label files` exposes file
pairing plus label field, placement method, target event / time, label unit, duration field and
check status. Focused tests now cover placement / duration preservation for epoch handoff,
inside-EEG source selection suppressing external label-file choices, and removing a loaded label
source from `Load Labels`. Follow-up coverage also verifies that auto-detected label carriers can
be removed from `Load Labels` and are excluded from the backend candidate through
`excluded_label_carriers`. Background test coverage now adds single-file selected-scope regressions
for sibling EEG files and service apply. Follow-up tests verify that class maps inferred from
external label carriers are not shown or saved when the user chooses `Labels inside EEG files`.
Offscreen screenshots include:

- `artifacts/ui/data-import-wizard-steps/04-match-labels-final-loaded-label-files.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-internal-suggested-events-full.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-bids-events.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-conversion-fallback.png`

2026-05-13 Tier 1/Tier 2 Data Import coverage adds:

- single-file selected-scope tests that still detect same-stem label carriers from nearby
  `label/` subfolders without importing sibling EEG files;
- BIDS-like `events.tsv` warning coverage for missing sidecar, missing duration, and missing
  onset blocking;
- internal-event evidence coverage for response/comment filtering and run-dependent `T1` / `T2`
  warnings;
- external label placement coverage that blocks invalid selected target events and preserves
  selected event filters into reviewed label import recipe state;
- UI coverage for BIDS-like event review cards and refreshed canonical wizard screenshots via
  `scripts/dev/capture_data_import_wizard_steps.py`.

Latest focused validation for this slice:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_data_interpretation_scan.py \
  tests/unit/backend/application/test_data_interpretation_label_carriers.py \
  tests/unit/backend/application/test_data_interpretation_candidate.py \
  tests/unit/backend/application/test_data_interpretation_recipe.py \
  tests/unit/backend/application/test_data_interpretation_review.py \
  tests/unit/backend/application/test_application_service.py -q
# 109 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/scripts/test_capture_data_interpretation_replay.py -q
# 69 passed
```

2026-05-14 Epoch handoff coverage adds a focused bridge from Data Import review choices into the
Create Epochs dialog:

- reviewed internal EEG labels record recommended class events for epoching;
- reviewed external label files record placement method, label field, target event selection,
  time field, duration/end field, class map and duration statistics as runtime epoch hints;
- interval labels using an end-time column are converted to durations before apply;
- reviewed event-code label carriers remap matching EEG events instead of falling back to sequence
  apply;
- Create Epochs consumes the import hint for suggested events, time window and baseline defaults,
  while keeping the old epoch dialog API compatible;
- Create Epochs section titles use card headers instead of Qt group-box legends, avoiding title /
  border overlap in the dark theme.

Focused validation for this slice:

```bash
poetry run ruff check \
  XBrainLab/backend/application/epoch_context.py \
  XBrainLab/backend/application/data_interpretation_apply.py \
  XBrainLab/backend/application/data_interpretation_service.py \
  XBrainLab/backend/load_data/label_loader.py \
  XBrainLab/ui/dialogs/preprocess/epoching_dialog.py \
  tests/unit/backend/application/test_epoch_context.py \
  tests/unit/backend/application/test_application_service.py \
  tests/integration/ui/test_dialog_acceptance.py
# All checks passed!

poetry run basedpyright \
  XBrainLab/backend/application/epoch_context.py \
  XBrainLab/backend/application/data_interpretation_apply.py \
  XBrainLab/backend/application/data_interpretation_service.py \
  XBrainLab/backend/load_data/label_loader.py \
  XBrainLab/ui/dialogs/preprocess/epoching_dialog.py \
  tests/unit/backend/application/test_epoch_context.py \
  tests/unit/backend/application/test_application_service.py \
  tests/integration/ui/test_dialog_acceptance.py
# 0 errors, 0 warnings, 0 notes

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_epoch_context.py \
  tests/unit/backend/application/test_application_service.py \
  tests/unit/backend/application/test_preprocess_service.py \
  tests/integration/ui/test_dialog_acceptance.py \
  tests/unit/ui/components/test_dialogs.py::test_epoching_dialog_init \
  tests/unit/ui/test_dialogs_extra.py::TestEpochingDialog \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_accepted \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_legacy_result_refreshes_shared_status \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_epoch_capability_not_preprocess_block \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_query_data_list_before_stale_controller \
  tests/unit/ui/preprocess/test_preprocess_panel.py::test_preprocess_panel_epoching \
  tests/unit/backend/load_data/test_label_loader.py \
  tests/unit/backend/load_data/test_label_loader_coverage.py -q
# 101 passed
```

Screenshot evidence:

- `artifacts/ui/epoching-dialog/epoching-interval-import.png`
- `artifacts/ui/epoching-dialog/epoching-internal-events.png`

2026-05-22 manual-test follow-up:

- Create Epochs now keeps its action footer fixed while the content area scrolls above it, so
  dense import hints / event lists do not push the Time Window card below the visible dialog.
- Data Import Review and Import now groups repeated file-scoped action items with the same target
  step, issue and next action into one review card / tree row, while preserving ordinary non-file
  review rows as separate items.
- Follow-up grouping now treats file-scoped review items as the same problem even when the file
  name appears in the issue/title rather than only in the impact text. The UI shows one card with
  affected files instead of one repeated card per EEG file.
- Load Labels rescan follow-up now resumes the wizard at Review Metadata after a user loads a
  new label source and presses Next, instead of rebuilding the dialog back at Choose EEG Data.
- Load Labels now supports in-place label-source rescan through the same command API, so the
  visible dialog stays open while refreshed label carriers are loaded and the wizard advances to
  Review Metadata without a close/reopen flash.
- Review and Import now refreshes its Import Summary from current wizard state when the final
  step is shown, so manual subject/session/task/run edits made in Review Metadata are reflected
  before applying.
- Load Labels now removes the containing user-loaded folder source when the removed label file is
  the only active carrier from that folder, so duplicate auto/folder label paths do not require a
  second removal. Multi-file folders keep the folder source and only exclude the selected file.
- Evaluation Metrics Summary now forces a dark selected-row palette, including inactive selection
  state, so selected rows do not fall back to unreadable white system selection colors.
- Visualization 3D Plot now blocks known-unstable Wayland / remote OpenGL PyVistaQt sessions before
  creating `QtInteractor`, so opening the last saliency tab shows a product message instead of
  risking a native crash.

Focused validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_dialogs_extra.py::TestEpochingDialog::test_content_scrolls_above_fixed_footer \
  tests/unit/ui/test_dialogs_extra.py::TestEpochingDialog::test_label_backgrounds_are_transparent \
  tests/unit/ui/components/test_dialogs.py::test_epoching_dialog_init \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_review_and_import_groups_repeated_file_action_items -q
# 4 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_dialogs_extra.py \
  tests/unit/ui/components/test_dialogs.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_ui_misc.py -q
# 266 passed

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/run_tests.py ui
# 1171 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q
# 71 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_dialogs_extra.py \
  tests/unit/ui/components/test_dialogs.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_ui_misc.py -q
# 268 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_rescans_after_add_label_folder_product_flow -q
# 74 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_dialogs_extra.py \
  tests/unit/ui/components/test_dialogs.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_ui_misc.py -q
# 272 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q
# 76 passed
```

## Backend Test Hygiene Inventory

2026-05-11 compact inventory for the backend/test hygiene branch:

| Cluster | Classification | Current evidence | Action in this branch |
| --- | --- | --- | --- |
| Data Interpretation backend lifecycle | Strong behavior tests | `tests/unit/backend/application/test_data_interpretation_service.py` covers scan -> preview -> validate -> apply, external label sources, selected file scope, metadata apply, label import recipe state. `tests/integration/backend/test_application_service_workflow.py` covers non-mocked ApplicationService interpretation -> recipe reload -> dataset workflow. | Strengthened selected-scope and service apply coverage; added relative selected-file normalization coverage. |
| Scan / candidate / review / recipe contracts | Useful unit contract tests | `test_data_interpretation_scan.py`, `test_data_interpretation_candidate.py`, `test_data_interpretation_review.py`, `test_data_interpretation_recipe.py`, `test_data_interpretation_label_carriers.py`. | Preserves BIDS/file/folder scan behavior, selected scope, external label source provenance, structured action items, recipe reload/remap, label source mode, placement, duration, and class-map source. |
| Product runtime BackendFacade guard | Strong architecture guard | `tests/architecture_compliance.py` now has a pytest gate that scans `XBrainLab/ui`, `XBrainLab/llm`, and `XBrainLab/mcp` for `BackendFacade` imports / construction. `tests/unit/test_architecture_compliance.py` covers both violation and allowed `get_application_service(study)` cases. | Product runtime packages must enter via `ApplicationService / Command API`; `BackendFacade` module is physically removed and must not return. |
| UI command route | Mock-heavy but useful command contract tests | `tests/unit/ui/test_ui_misc.py` asserts import file/folder/BIDS/reload route through `ScanSourceCommand`, `PreviewInterpretationCommand`, `ValidateInterpretationCommand`, and `ApplyInterpretationCommand` without controller import fallback. `tests/unit/ui/dataset/test_dataset_sidebar.py` and `test_panel.py` guard real-Study fallback refusal. | Backend/test continuation adds command-route coverage only. The current dirty worktree still contains earlier Load Labels / Match Labels UX edits, so product UI acceptance must be judged separately from these route tests. |
| Agent / MCP command parity | Useful contract and adapter tests | `tests/unit/llm/tools/test_application_surface.py`, `tests/unit/llm/tools/real/test_real_tools.py`, `tests/unit/llm/tools/test_definitions.py`, `tests/unit/llm/agent/test_tool_call_normalizer.py`, `tests/unit/mcp/test_server.py`, and `tests/integration/mcp/*` cover exposed Data Interpretation command names, confirmation boundary, blocked reasons, schema exposure, and state truth. Broader LLM/root/integration tests that previously patched removed real-tool `BackendFacade` symbols now patch `get_application_service` and assert command objects / command results. | Real agent tools now assert `ApplicationService` command objects instead of patching `BackendFacade`; tool schema, MCP tools/list, and real/mock tool surfaces carry `label_sources` and the shared choice schema. |
| Real-data fixture validation | Strong integration evidence when fixtures are present | Real-data tests now resolve fixtures under `tests/fixtures/data/`; scripts use the same path. | Replaced obsolete `tests/data/` path references so deleted tracked fixture files do not turn IO/pipeline tests into false skips. The replacement fixture tree must be included in the PR rather than left untracked. |
| Legacy direct controller tests | Mock-heavy but useful compatibility tests | Legacy controller fallback tests remain in UI suites to guard mock/legacy contexts and real-Study refusal. | Not deleted; retained because they protect compatibility while architecture guards prevent product fallback bypass. |
| Obsolete / duplicated clusters | Obsolete path cluster | The obsolete cluster is the deleted `tests/data/` fixture location, replaced by `tests/fixtures/data/`. No test cluster was deleted without replacement. | Consumers and docs were moved to `tests/fixtures/data/`; real-data gates must use that path. |
| Missing coverage outside this scope | Explicitly out of current backend/test cleanup scope | Full internal event-name extraction for every EEG format, Windows human desktop acceptance, and final Epoch UI consumption of `duration_field`. | Documented as future validation/product work, not claimed by this branch. |

## 常用 docs gate

```bash
poetry run mkdocs build --strict
git diff --check
```

如果改 CSS / layout，還要留下 built site screenshot 或可視覺審核 artifact。
