# XBrainLab 驗證策略

最後更新：`2026-05-16`

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

## Backend Test Hygiene Inventory

2026-05-11 compact inventory for the backend/test hygiene branch:

| Cluster | Classification | Current evidence | Action in this branch |
| --- | --- | --- | --- |
| Data Interpretation backend lifecycle | Strong behavior tests | `tests/unit/backend/application/test_data_interpretation_service.py` covers scan -> preview -> validate -> apply, external label sources, selected file scope, metadata apply, label import recipe state. `tests/integration/backend/test_application_service_workflow.py` covers non-mocked ApplicationService interpretation -> recipe reload -> dataset workflow. | Strengthened selected-scope and service apply coverage; added relative selected-file normalization coverage. |
| Scan / candidate / review / recipe contracts | Useful unit contract tests | `test_data_interpretation_scan.py`, `test_data_interpretation_candidate.py`, `test_data_interpretation_review.py`, `test_data_interpretation_recipe.py`, `test_data_interpretation_label_carriers.py`. | Preserves BIDS/file/folder scan behavior, selected scope, external label source provenance, structured action items, recipe reload/remap, label source mode, placement, duration, and class-map source. |
| Product runtime BackendFacade guard | Strong architecture guard | `tests/architecture_compliance.py` now has a pytest gate that scans `XBrainLab/ui`, `XBrainLab/llm`, and `XBrainLab/mcp` for `BackendFacade` imports / construction. `tests/unit/test_architecture_compliance.py` covers both violation and allowed `get_application_service(study)` cases. | Product runtime packages must enter via `ApplicationService / Command API`; `BackendFacade` remains legacy compatibility only. |
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
