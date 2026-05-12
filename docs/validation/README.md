# XBrainLab 驗證策略

最後更新：`2026-05-13`

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

- `artifacts/ui/data-import-wizard-steps/01-choose-eeg-data.png`
- `artifacts/ui/data-import-wizard-steps/02-load-labels-many.png`
- `artifacts/ui/data-import-wizard-steps/03-review-metadata.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-internal-suggested-events-full.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-final-loaded-label-files.png`
- `artifacts/ui/data-import-wizard-steps/05-review-and-import.png`

## 2026-05-13 Data Import Runtime Integration Checkpoint

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `72 passed` | Product runtime and product-success tests still do not contain guarded `BackendFacade` or legacy fallback regressions after the Data Import UX checkpoint integration. | Semantic proof for code outside guarded paths or human runtime acceptance. | Keep extending guard examples when new UI/backend adapters appear. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_label_carriers.py tests/unit/backend/application/test_data_interpretation_review.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q` | `98 passed` | Data Interpretation preview/review/service contracts and current Data Import dialog behavior remain green with the placement-evidence checkpoint. | Final Match Labels UX or human desktop acceptance. | Keep remaining Match Labels / Review and Import UX debt explicit. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/backend/application -q` | `170 passed` | Focused ApplicationService and command-service contracts remain green after integration. | Full product acceptance. | Keep command-service tests as the main backend regression floor. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/llm/tools tests/unit/mcp -q` | `238 passed` | Agent tool and MCP command surfaces remain aligned with ApplicationService command truth. | Tool-call benchmark accuracy or external client certification. | Run tool-call eval only after product stabilization. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` | `8 passed` | Non-mocked ApplicationService workflow coverage remains green. | All data formats or human UI workflow acceptance. | Keep real workflow tests paired with UI smoke evidence. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_application_capabilities.py tests/unit/ui/test_sidebars_and_components.py tests/unit/ui/test_ui_misc.py -q` | `275 passed` | UI command/refresh helpers and sidebar command-route coverage remain green. | Final desktop UX or full read-only controller removal. | Continue human-observable desktop smoke work after docs/site closure. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Canonical docs and artifact index edits build strictly and have clean whitespace. | Documentation content is automatically correct. | Keep docs tied to runtime validation evidence. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 01:16:05 UTC+08:00`. | Fast engineering dashboard is green after integration, including full lint/type, architecture, startup, UI baseline, UI unit suite, and real-data IO. | Product complete or human Windows acceptance. | Human-observable desktop product smoke remains required before release claims. |

## Backend Test Hygiene Inventory

2026-05-11 compact inventory for the backend/test hygiene branch:

| Cluster | Classification | Current evidence | Action in this branch |
| --- | --- | --- | --- |
| Data Interpretation backend lifecycle | Strong behavior tests | `tests/unit/backend/application/test_data_interpretation_service.py` covers scan -> preview -> validate -> apply, external label sources, selected file scope, metadata apply, label import recipe state. `tests/integration/backend/test_application_service_workflow.py` covers non-mocked ApplicationService interpretation -> recipe reload -> dataset workflow. | Strengthened selected-scope and service apply coverage; added relative selected-file normalization coverage. |
| Scan / candidate / review / recipe contracts | Useful unit contract tests | `test_data_interpretation_scan.py`, `test_data_interpretation_candidate.py`, `test_data_interpretation_review.py`, `test_data_interpretation_recipe.py`, `test_data_interpretation_label_carriers.py`. | Preserves BIDS/file/folder scan behavior, selected scope, external label source provenance, structured action items, recipe reload/remap, label source mode, placement, duration, and class-map source. |
| Product runtime BackendFacade guard | Strong architecture guard | `tests/architecture_compliance.py` scans `XBrainLab/ui`, `XBrainLab/llm`, and `XBrainLab/mcp` for `BackendFacade` imports / construction, scans product-success integration suites for `BackendFacade` workflow evidence, and rejects any test-side `BackendFacade` import / construction. `tests/unit/test_architecture_compliance.py` covers forbidden runtime/test examples. | Product runtime packages and tests must enter via `ApplicationService / Command API`; `BackendFacade` is physically removed. |
| Product-success legacy fallback guard | Strong architecture guard | `tests/architecture_compliance.py` now also scans product-success integration suites for `run_legacy_controller_fallback()` and `get_legacy_controller_from_study()` usage. `tests/unit/test_architecture_compliance.py` covers forbidden integration examples and allowed unit compatibility examples. | Integration tests must not bless legacy fallback helpers as product success; legacy fallback coverage remains unit compatibility only. |
| UI command route | Mock-heavy but useful command contract tests | `tests/unit/ui/test_ui_misc.py` asserts import file/folder/BIDS/reload route through `ScanSourceCommand`, `PreviewInterpretationCommand`, `ValidateInterpretationCommand`, and `ApplyInterpretationCommand` without controller import fallback. `tests/unit/ui/dataset/test_dataset_sidebar.py` and `test_panel.py` guard real-Study fallback refusal. | Backend/test continuation adds command-route coverage only. The current dirty worktree still contains earlier Load Labels / Match Labels UX edits, so product UI acceptance must be judged separately from these route tests. |
| Agent / MCP command parity | Useful contract and adapter tests | `tests/unit/llm/tools/test_application_surface.py`, `tests/unit/llm/tools/real/test_real_tools.py`, `tests/unit/llm/tools/test_definitions.py`, `tests/unit/llm/agent/test_tool_call_normalizer.py`, `tests/unit/mcp/test_server.py`, and `tests/integration/mcp/*` cover exposed Data Interpretation command names, confirmation boundary, blocked reasons, schema exposure, and state truth. Broader LLM/root/integration tests that previously patched removed real-tool `BackendFacade` symbols now patch `get_application_service` and assert command objects / command results. | Real agent tools now assert `ApplicationService` command objects instead of patching `BackendFacade`; tool schema, MCP tools/list, and real/mock tool surfaces carry `label_sources` and the shared choice schema. |
| Real-data fixture validation | Strong integration evidence when fixtures are present | Real-data tests now resolve fixtures under `tests/fixtures/data/`; scripts use the same path. | Replaced obsolete `tests/data/` path references so deleted tracked fixture files do not turn IO/pipeline tests into false skips. The replacement fixture tree must be included in the PR rather than left untracked. |
| Legacy direct controller tests | Mock-heavy but useful compatibility tests | Legacy controller fallback tests remain in UI suites to guard mock/legacy contexts and real-Study refusal. | Not deleted; retained because they protect compatibility while architecture guards prevent product fallback bypass. |
| Obsolete / duplicated clusters | Obsolete path cluster | The obsolete cluster is the deleted `tests/data/` fixture location, replaced by `tests/fixtures/data/`. No test cluster was deleted without replacement. | Consumers and docs were moved to `tests/fixtures/data/`; real-data gates must use that path. |
| Missing coverage outside this scope | Explicitly out of current backend/test cleanup scope | Full internal event-name extraction for every EEG format, Windows human desktop acceptance, and final Epoch UI consumption of `duration_field`. | Documented as future validation/product work, not claimed by this branch. |

## 2026-05-12 Backend Runtime Zero-Legacy Closure

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run python tests/architecture_compliance.py` and `poetry run pytest --capture=sys tests/architecture_compliance.py -q` | PASS, `Architecture compliant!` / `1 passed` | Product runtime and product-success tests do not contain known `BackendFacade` / controller fallback regressions covered by guards. | Manual runtime acceptance for every UI branch. | Keep adding realistic forbidden examples when a new adapter path appears. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `58 passed` | Architecture guard behavior is covered, including product-success `BackendFacade` test rejection. | Semantic proof for code outside scanned dirs. | Extend scanned dirs when product evidence moves. |
| `poetry run pytest --capture=sys tests/unit/backend/application -q` | `142 passed` | Command services, state snapshots, capability/result contracts remain intact. | UI ergonomics or desktop acceptance. | Keep focused service tests with each command slice. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` | `8 passed` | Non-mocked ApplicationService workflows include dialog-like dataset split generation and downstream `TRAIN` readiness. | Every possible split strategy or external dataset. | Add real failing split fixtures as they appear. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/dialogs/test_data_splitting.py tests/unit/ui/test_sidebars_and_components.py -k split_data -q` | `13 passed, 113 deselected` | Data Splitting dialog defaults no longer generate disabled test/validation splits, and sidebar split action still routes correctly. | Data Import UX redesign or human click-through. | Human desktop smoke still needed. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py tests/unit/backend/application/test_state_service.py tests/unit/llm/agent/test_context_assembler.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/tools tests/unit/mcp -q` | `281 passed` | Agent/MCP tool gating, stage assembly, and command surface remain aligned with ApplicationService truth. | Tool-call benchmark accuracy. | Re-run optional eval only after product stabilization. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` | `31 passed, 8 warnings` | Real-data import product evidence uses ApplicationService command import instead of BackendFacade success. | Full format support or clean warning-free MNE parsing. | Warnings remain format-library/runtime metadata notes. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_checked_in_real_dataset_validation.py tests/integration/pipeline/test_public_cross_source_training_smoke.py -q` | `10 passed, 3 warnings` | Real-data dataset generation and training smokes use ApplicationService commands and sync `TrainCommand`. | Training quality claim. | Add longer training only for thesis/evidence phase. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q` | `2 passed` | Representative pipeline smoke still works after command-boundary changes. | Complete desktop workflow. | Keep as minimal regression gate. |
| `poetry run ruff check <changed Python files>` / `poetry run basedpyright <changed Python files>` / `poetry run basedpyright` | PASS / `0 errors, 0 warnings, 0 notes` / `0 errors, 0 warnings, 0 notes` | Changed code and full repo pass lint/type gates. | Runtime behavior by itself. | Keep full type gate before goal closure when feasible. |
| `poetry run mkdocs build --strict` | PASS after docs closure. | Documentation site builds strictly. | Content is automatically correct. | Keep docs updates tied to validation evidence. |
| `poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-12 12:23:48 UTC+08:00` | Fast engineering dashboard is green, including full lint/type, architecture, startup, UI baseline/dialog/unit, real-data IO. | Product complete, release approval, human Windows acceptance. | Run human-observable product smoke next. |

## 2026-05-12 Epoch UI Freeze Reality-Gap Closure

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Offscreen MainWindow probe loading `tests/fixtures/data/A01T.gdf`, `A02T.gdf`, `A03T.gdf`, then running all-event `open_epoching()` through `ApplicationService` | Before fix, command and refresh returned in about `5.4s`, then product path still called blocking `QMessageBox.information`. | User-reported freeze was not a backend command crash; the command reached `Dataset locked`, and the UI risk was post-command blocking modal / queued refresh behavior. | Exact Windows human click-through conditions, screen placement, or dual-monitor modal visibility. | Keep a human desktop rerun as acceptance evidence before release claims. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_panel.py::test_update_panel_epoched_data_cancels_pending_plot_timer tests/unit/ui/preprocess/test_preprocess_panel.py::test_update_plot_only_epoched_data_shows_locked_message_without_plotting tests/integration/ui/test_epoch_runtime.py::test_real_gdf_epoching_does_not_block_on_success_modal -q` | Red before fix, then `3 passed`. | Epoched preprocess preview cancels pending redraws, queued plot refresh does not render epochs, and real-GDF product command success does not open a blocking success modal. | Full desktop UX, all EEG formats, or long assistant session stability. | Expand product smoke when the full MVP workflow is finalized. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/preprocess -q` | `51 passed`. | Preprocess panel/dialog behavior remains intact after the locked-preview guard. | Product completion. | Keep real-data smoke for reported runtime failures. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py -q` | `96 passed`. | Sidebar legacy/mock compatibility and command-route tests still pass. | Human Windows acceptance. | Continue replacing weak product-success evidence with command-backed tests. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/preprocess/test_preprocess_performance.py tests/unit/ui/test_sidebars_and_components.py -k 'epoching or preprocess_panel or update_plot_only or plot_timer or debouncing' tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions tests/integration/ui/test_epoch_runtime.py -q` | `28 passed, 92 deselected`. | Focused product walkthrough and epoch/debounce paths remain green together. | Broad UI acceptance. | Run broader dashboard before branch closure. |
| `poetry run ruff check <changed Python files>` / `poetry run basedpyright <changed Python files>` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed implementation and tests pass focused lint/type gates. | Full repo health by itself. | Run final docs/dashboard gates before merge. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS. | Canonical docs still build and diff whitespace is clean. | Content is automatically complete. | Keep docs tied to product evidence. |
| `poetry run python tests/architecture_compliance.py` / `poetry run basedpyright` | `Architecture compliant!` / `0 errors, 0 warnings, 0 notes`. | Product runtime architecture guard and full type gate remain green. | Human runtime acceptance. | Keep architecture guard examples updated when new product paths appear. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-12 13:31:22 UTC+08:00`. | Fast engineering dashboard remains green after the Epoch UI freeze fix. | Product complete, release approval, or human Windows acceptance. | Human desktop rerun still needed before release claims. |

## 2026-05-12 Backend Command-Spine Hardening Follow-Up

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_application_capabilities.py tests/unit/test_architecture_compliance.py -q` | `146 passed` | Command result envelope, read-only state preservation, UI command observer suppression, and architecture guard examples are covered. | Full desktop acceptance. | Keep adding guard examples for each newly found bypass. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/mcp/test_server.py tests/unit/mcp/test_http_server.py tests/unit/backend/application/test_automation.py -q` | `68 passed` | Agent / MCP command surface still consumes structured ApplicationService results after contract hardening. | Tool-call benchmark accuracy or client certification. | Defer thesis eval until product surface is stable. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py tests/integration/ui/test_epoch_runtime.py tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions -q` | Red first because the walkthrough did not simulate Start Training confirmation and its fake `start_training()` did not accept `append` / `interactive`; after test alignment, `10 passed`. | Product walkthrough now exercises command confirmation and the current `TrainCommand` controller-call contract. | Human Windows click-through or long training acceptance. | Keep offscreen walkthrough aligned with backend command contract. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q` | `2 passed` | Representative pipeline smoke still works after command-spine hardening. | Training quality or product completion. | Keep as a small regression gate. |
| `poetry run ruff check .` / `poetry run basedpyright` / `poetry run python tests/architecture_compliance.py` / `git diff --check` | PASS / `0 errors, 0 warnings, 0 notes` / `Architecture compliant!` / PASS | Full lint/type/static architecture/whitespace gates are green for this slice. | Runtime acceptance by itself. | Run docs and dashboard gates after docs closure. |
| `poetry run mkdocs build --strict` / `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | PASS / Dashboard `PASS`, generated `2026-05-12 14:30:33 UTC+08:00` | Docs build strictly and the fast engineering dashboard is green, including full lint/type, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete, release approval, or human Windows acceptance. | Human-observable desktop smoke remains required before release claims. |

## 2026-05-12 Backend/UI Legacy Test Hygiene Follow-Up

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `64 passed` | Architecture guard unit coverage includes product-success legacy fallback rejection and unit legacy compatibility allowance. | Runtime correctness or semantic proof outside scanned dirs. | Add concrete forbidden examples when new product evidence paths appear. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!` | Current product runtime and product-success integration suites do not contain known `BackendFacade` or legacy fallback product-evidence bypasses covered by the guards. | Human Windows desktop acceptance. | Keep guard scope aligned with product-evidence directories. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py -q` | `96 passed` | Sidebar command-route and legacy mock-context compatibility tests remain green after renaming weak legacy tests and adding behavior assertions. | Product UI completion or real desktop click-through. | Continue replacing ambiguous mock-only tests with explicit behavior/state/command assertions. |
| `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py tests/unit/ui/test_sidebars_and_components.py` / `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py tests/unit/ui/test_sidebars_and_components.py` | PASS / `0 errors, 0 warnings, 0 notes` | Changed tests and architecture guard pass focused lint/type gates. | Full repo health by itself. | Run docs gate after docs closure. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Documentation edits build strictly and diff whitespace is clean. | Documentation content is automatically complete. | Keep future validation entries tied to executed commands. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py -q` | `96 passed` after PreprocessSidebar cleanup. | PreprocessSidebar filtering/resample/rereference/normalize/epoching mock-context tests now explicitly assert attempted command routing plus legacy controller fallback parameters. | Product command success or human desktop acceptance. | Continue with remaining ambiguous `accepted` / `no_crash` UI unit tests. |
| `poetry run ruff check tests/unit/ui/test_sidebars_and_components.py` / `poetry run basedpyright tests/unit/ui/test_sidebars_and_components.py` | PASS / `0 errors, 0 warnings, 0 notes` | The focused UI test cleanup passes lint/type gates. | Full repo health by itself. | Run docs gate before committing this slice. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py -q` | `96 passed` after TrainingSidebar accepted-test cleanup. | TrainingSidebar model-selection and training-setting mock-context tests now explicitly assert attempted `ConfigureTrainingCommand` routing plus legacy controller fallback parameters. | Product command success or human desktop acceptance. | Remaining ambiguous names in this file are `test_update_info_no_crash` and `test_open_channel_selection_accepted`. |
| `poetry run ruff check tests/unit/ui/test_sidebars_and_components.py` / `poetry run basedpyright tests/unit/ui/test_sidebars_and_components.py` | PASS / `0 errors, 0 warnings, 0 notes`. | The TrainingSidebar test cleanup passes focused lint/type gates. | Full repo health by itself. | Keep replacing ambiguous test names with behavior-specific coverage. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py -q` | `96 passed` after final ambiguous-name cleanup. | The file no longer has `accepted` / `no_crash` test names. TrainingSidebar `update_info` now asserts the info-panel service boundary, and DatasetSidebar channel selection mock-context coverage asserts `QueryStateCommand`, `PreprocessCommand`, and legacy fallback behavior. | Product command success or human desktop acceptance. | Continue scanning other suites for weak names or mock-only assertions. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/styles/test_theme.py tests/unit/ui/test_data_splitting.py tests/unit/ui/training/test_test_only_setting.py tests/unit/ui/test_ui_misc.py::TestAgentManagerDeep::test_open_montage_legacy_mock_context_applies_controller_fallback -q` | `78 passed`. | The remaining `accepted` / `no_crash` names in focused UI unit files were replaced with behavior-specific assertions for ignored `None` matplotlib figures, accepted split preview results, accepted device dialog result, and mock-context montage controller fallback. | Full UI acceptance. | Keep weak-name scan in branch closure checks. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py -q` | `143 passed`. | The broader `test_ui_misc.py` file remains green after the AgentManager montage test clarification. | Full product UX or local LLM runtime. | Continue with broader dashboard at branch closure. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `68 passed`. | Architecture guard unit coverage now includes the weak-test-name guard for `accepted`, `no_crash`, and `does_not_crash` placeholders. | Semantic proof outside scanned test files. | Keep the guard aligned with allowed behavior-specific naming. |
| `poetry run python tests/architecture_compliance.py` / `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py` / `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py` | `Architecture compliant!` / PASS / `0 errors, 0 warnings, 0 notes`. | The repo currently has no guarded weak test names, and the guard implementation passes focused lint/type checks. | Product runtime acceptance or test strength beyond the guarded naming pattern. | Continue strengthening mock-heavy assertions; naming guard is only a floor. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `70 passed`. | Architecture guard unit coverage now requires allowed `BackendFacade` quarantine tests to carry the registered `facade_compatibility` marker. | Runtime correctness or facade removal readiness by itself. | Keep replacement coverage in ApplicationService tests; marker is only quarantine labeling. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py tests/unit/backend/application/test_runtime.py -q` | `47 passed`. | Existing facade-only compatibility/runtime tests remain green after explicit `facade_compatibility` labeling. | Product runtime success; these tests are explicitly not product-success evidence. | Continue deleting facade compatibility coverage once command/service replacement tests are complete. |
| `poetry run python tests/architecture_compliance.py` / focused `ruff` / focused `basedpyright` for architecture and facade marker files | `Architecture compliant!` / PASS / `0 errors, 0 warnings, 0 notes`. | The registered marker and quarantine guard are static-clean. | Human Windows desktop acceptance. | Include architecture gate in branch closure. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_headless.py -q` | `6 passed` after split; baseline was `1 passed` before the split. | Facade headless compatibility coverage is now behavior-specific and no longer depends on hidden state shared inside one monolithic test. | Product runtime success; this remains facade compatibility coverage. | Continue replacing facade-only coverage with command/service tests where product behavior still lacks direct coverage. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py tests/unit/backend/application/test_runtime.py -q` | `52 passed`. | The facade compatibility/runtime cluster remains green after splitting the headless test. | Product runtime usage of facade. | Keep the cluster quarantined until physical facade removal. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py -q` | `43 passed`. | Facade coverage naming now explicitly describes legacy compatibility behavior, including montage match/verification cases and clear-data delegation. | Product workflow evidence. | Continue moving durable behavior coverage to command/service tests. |
| `poetry run pytest --capture=sys tests/unit/ui/dialogs/test_export_saliency.py -q` | Red first with `17 errors` from a `backend.visualization` / `training_plan` circular import; after moving saliency method names to a lightweight module and strengthening assertions, `17 passed`. | ExportSaliencyDialog imports cleanly and its weak no-crash paths now assert combo state, warning behavior, export cancellation, success notification, and accept/no-accept boundaries. | Human visual acceptance or real saliency artifact quality. | Keep broader visualization/UI tests in branch closure. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/dialogs/test_export_saliency.py tests/unit/ui/dialogs/test_saliency_setting.py tests/unit/ui/components/test_plot_figure_window.py -q` / `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py -q` | `39 passed` / `17 passed`. | Adjacent saliency UI import and sidebar tests remain green after the saliency-method import split. | Full visualization workflow acceptance. | Continue focused UI hygiene without redesigning visualization UX. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_visualization.py -q` | `18 passed`. | Saliency map widget data-path coverage now asserts visualizer invocation, figure replacement, canvas ownership, and hidden error state instead of swallowing generic matplotlib exceptions. | Real visual artifact correctness. | Continue cleaning remaining weak UI comments. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/chat/test_message_bubble.py -q` | `9 passed`. | MessageBubble file-link coverage now asserts Windows Explorer selection and non-Windows desktop-service behavior as separate side effects. | Full chat panel acceptance. | Continue cleaning the remaining weak UI comment in info-panel service coverage. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/components/test_info_panel_service.py -q` | `7 passed`. | InfoPanelService initialization now asserts dataset/preprocess observer bridge observables and event names instead of relying on construction without error. | Full MainWindow refresh acceptance. | Keep broader UI refresh tests in branch closure. |
| `poetry run pytest --capture=sys tests/unit/backend/utils/test_montage_mapping.py tests/unit/backend/test_facade_coverage.py -q` | `50 passed`. Full `test_facade_coverage.py` was red before fixing its helper because it created a mocked study but did not pass it into `BackendFacade`; after fixture correction the file is `43 passed`. | Montage fuzzy matching now has direct backend helper coverage outside `BackendFacade`, and facade compatibility tests actually exercise their mocked-study boundary. | Product runtime completion or human desktop acceptance. | Continue deleting or moving facade-only compatibility tests only after their command/service replacements are confirmed. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py tests/unit/backend/application/test_runtime.py tests/unit/backend/utils/test_montage_mapping.py -q` | `54 passed`. | Facade compatibility coverage, headless construction, shared service cache, and the extracted montage helper are mutually green after mocked-study fixture correction. | Product runtime usage of facade; architecture guard still treats facade as legacy-only. | Keep facade compatibility tests quarantined under unit tests until removal. |
| `poetry run ruff check XBrainLab/backend/utils/montage_mapping.py XBrainLab/backend/facade.py tests/unit/backend/utils/test_montage_mapping.py tests/unit/backend/test_facade_coverage.py` / `poetry run basedpyright XBrainLab/backend/utils/montage_mapping.py XBrainLab/backend/facade.py tests/unit/backend/utils/test_montage_mapping.py tests/unit/backend/test_facade_coverage.py` | PASS / `0 errors, 0 warnings, 0 notes`. | The montage helper, facade adapter, and compatibility tests pass focused lint/type gates. | Full repo health by itself. | Run broader dashboard only at branch closure or when product runtime scope changes. |
| `poetry run ruff check tests/unit/backend/test_facade_headless.py tests/unit/backend/application/test_runtime.py` / `poetry run basedpyright tests/unit/backend/test_facade_headless.py tests/unit/backend/application/test_runtime.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Headless facade compatibility and runtime cache tests pass focused lint/type gates. | Full repo health by itself. | Keep these tests as compatibility/runtime-only evidence. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `66 passed`. | Architecture guard unit coverage now includes a `BackendFacade` test-quarantine rule: only explicit facade compatibility/runtime/guard tests may import or instantiate `BackendFacade`. | Semantic proof outside scanned test files. | Add allowed files only with replacement-coverage rationale. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!` after the quarantine rule. | Current repo has no `BackendFacade` usage outside the allowed unit compatibility/runtime/guard test quarantine and the facade module itself. | Product completion or human desktop acceptance. | Keep this gate in final branch validation. |
| `poetry run python tests/architecture_compliance.py` / `poetry run mkdocs build --strict` / `git diff --check` | `Architecture compliant!` / PASS with the existing MkDocs Material advisory / PASS. | Static architecture guard, docs build, and whitespace gate are clean for the montage-helper slice. | Human runtime acceptance or full repo dashboard health. | Continue with the next backend/test hygiene slice. |

## BackendFacade Retirement Map

2026-05-12 physical removal status:

| Former facade cluster | Removed facade-only tests | Replacement coverage status | Current note |
| --- | --- | --- | --- |
| Runtime construction / shared service cache | `tests/unit/backend/test_facade_headless.py`, facade case in `tests/unit/backend/application/test_runtime.py` | Covered for product runtime by `get_application_service(study)` cache tests, startup smoke, and architecture guard. | Keep `get_application_service` runtime tests; no facade wrapper remains. |
| Load data / attach labels / import labels | `TestLoadData`, `TestAttachLabels` in `test_facade_coverage.py` | Covered by `DataCompatibilityCommandService`, including direct attach-label no-match, loader-error, full-data-path mapping, and multi-file batch checks, ApplicationService IO integration, and checked-in label-attached pipeline smokes. | Product callers use command API; no old tuple facade API remains. |
| Metadata / smart parse / remove files | Thin facade methods in `test_facade_coverage.py` | Covered by data table command tests, state/query diagnostics tests, and UI command-route tests. | Preserve command result semantics, not facade method names. |
| Preprocess / epoch wrappers | `TestDelegation` preprocess methods in `test_facade_coverage.py` | Covered by `PreprocessCommandService`, including direct individual `NOTCH`, `RESAMPLE`, `NORMALIZE`, and channel-list `REREFERENCE` operation checks, `ApplicationService`, UI command-route, and real-data pipeline smokes. | Product preprocess/epoch entry is command backed. |
| Dataset generation / clear datasets | `TestGenerateDataset`, clear dataset tests in `test_facade_coverage.py` | Covered by dataset generation service tests, including direct `GenerateDatasetCommand` split-strategy (`trial` / `session` / `subject`) and training-mode (`individual` / `group`) mapping checks, ApplicationService workflow tests, and real-data pipeline smokes. | Keep service tests; do not preserve facade API as product evidence. |
| Training configure / start / stop / clear history | `test_backend_facade_headless`, `TestTrainingControl`, `TestDelegation` | Covered by training command service tests, including direct case-insensitive model, unknown-model rejection, AdamW optimizer, and `auto` device mapping checks, ApplicationService tests, and pipeline smokes. | Product training entry is command backed. |
| Evaluate / visualize / saliency summaries | `TestGetLatestResults` and summary helpers in `test_facade_coverage.py` | Covered by analysis command service tests, including no-results, multi-plan, finished-run, and `training_active` command diagnostics, plus ApplicationService tests. | Preserve command result semantics, not facade shape. |
| Montage fuzzy matching | `TestSetMontage` in `test_facade_coverage.py` | Fuzzy cleanup lives in `XBrainLab.backend.utils.montage_mapping` with direct helper tests. UI/dialog/tool paths still own interactive confirmation. | The highest-risk former facade-specific logic is now outside the removed facade. |

`XBrainLab/backend/facade.py`, `tests/unit/backend/test_facade_coverage.py`, and
`tests/unit/backend/test_facade_headless.py` are removed. `pyproject.toml` no longer registers a
`facade_compatibility` marker. Architecture compliance rejects any future test-side facade usage.

## 2026-05-12 Repo Weak Assertion Cleanup

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `rg -n -i "no crash|not crash|doesn't crash|does not crash|doesnt crash|just verify|just ensure|success if no error|should not raise|should not crash" tests --glob '*.py' --glob '!**/__pycache__/**'` | No matches. | The repo no longer has the scanned weak assertion wording in Python tests. | Test quality beyond this wording pattern. | Continue reviewing mock-heavy tests by behavior, not only by names/comments. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys <touched UI/backend/LLM/preprocessor/load-data/training integration tests> -q` | `585 passed`. | Strengthened tests remain green together after replacing weak no-crash/no-raise checks with explicit behavior assertions. | Full product runtime acceptance. | Keep using smaller focused subsets during future slices, then run a combined gate before commit. |
| `poetry run ruff check <changed Python files>` | PASS. | Changed Python files pass lint after the weak-assertion cleanup and small type annotations. | Full repo lint by itself. | Run full lint near branch closure or if shared product code changes broaden. |
| `poetry run basedpyright <changed Python files>` | `0 errors, 0 warnings, 0 notes`; `.basedpyright/baseline.json` reduced one stale `event_loader.py` baseline entry. | Changed files pass focused type checking, and the EventLoader annotation improvement reduced baseline debt. | Full repo type-debt removal. | Keep removing baseline entries only when the corresponding code is actually fixed. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `70 passed`. | Existing architecture and weak-test-name guards remain green after the cleanup. | Product runtime acceptance by itself. | Keep extending guard examples when new product-evidence paths appear. |
| `poetry run mkdocs build --strict` | PASS with the existing MkDocs Material advisory and nav notices. | Documentation edits build strictly. | Documentation content is automatically complete. | Keep validation records tied to executed commands. |
| `git diff --check` | PASS. | Current diff has no whitespace errors. | Docs build or runtime behavior. | Re-run after docs edits and before commit. |

## 2026-05-12 AgentManager Montage Command Route Guard

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestAgentManagerDeep::test_open_montage_command_route_skips_legacy_controller tests/unit/ui/test_ui_misc.py::TestAgentManagerDeep::test_open_montage_legacy_mock_context_applies_controller_fallback -q` | `2 passed`. | AgentManager montage command-route and legacy mock-context fallback behavior are both explicitly covered. | Human montage-dialog acceptance. | Keep command-route and compatibility tests paired until legacy fallback is removed. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py -q` | `144 passed`. | Broader UI misc coverage remains green after the montage guard. | Full product UI acceptance. | Run broader UI/dashboard gates at branch closure. |
| `poetry run ruff check tests/unit/ui/test_ui_misc.py` / `poetry run basedpyright tests/unit/ui/test_ui_misc.py` | PASS / `0 errors, 0 warnings, 0 notes`. | The focused test file remains lint/type clean. | Runtime behavior by itself. | Continue adding command-route assertions beside compatibility fallbacks. |
| `git diff --check` | PASS. | Current diff has no whitespace errors. | Docs build. | Re-run after docs edits and before commit. |

## 2026-05-12 Dataset Generation Facade-Replacement Guard

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/backend/application/test_dataset_generation_service.py -q` | `8 passed`. | Dataset-generation command service directly covers split strategy and training mode mapping that used to be represented in facade compatibility tests. | Product runtime acceptance or all external dataset variations. | Keep adding direct command/service replacement coverage before deleting facade tests. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/application/test_dataset_generation_service.py -q` | `51 passed`. | Legacy facade compatibility and direct replacement coverage remain green together. | Product runtime usage of facade; facade tests remain compatibility-only evidence. | Continue quarantining facade coverage until physical removal. |
| `poetry run ruff check tests/unit/backend/application/test_dataset_generation_service.py` / `poetry run basedpyright tests/unit/backend/application/test_dataset_generation_service.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed replacement tests pass focused lint/type gates. | Full repo quality by itself. | Run broader gates before branch closure. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!`. | Product runtime and product-success test architecture guards remain clean after the replacement test slice. | Human Windows desktop acceptance. | Keep this gate in each backend/test hygiene slice. |

## 2026-05-12 Training Configure Facade-Replacement Guard

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/backend/application/test_training_service.py -q` | `7 passed`. | Training command service directly covers model, optimizer, and device mapping behavior previously represented in facade compatibility tests. | Full training runtime quality or GPU acceptance. | Keep command-service coverage as the replacement when deleting facade tests. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/application/test_training_service.py -q` | `50 passed`. | Legacy facade compatibility and direct replacement coverage remain green together. | Product runtime usage of facade; facade tests remain compatibility-only evidence. | Continue quarantining facade coverage until physical removal. |
| `poetry run ruff check tests/unit/backend/application/test_training_service.py` / `poetry run basedpyright tests/unit/backend/application/test_training_service.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed replacement tests pass focused lint/type gates. | Full repo quality by itself. | Run broader gates before branch closure. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!`. | Product runtime and product-success test architecture guards remain clean after the replacement test slice. | Human Windows desktop acceptance. | Keep this gate in each backend/test hygiene slice. |

## 2026-05-12 Evaluation Latest-Results Facade-Replacement Guard

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py -q` | `6 passed`. | Analysis command service directly covers no-results, multi-plan, finished-run, and active-training evaluation summary behavior. | Full evaluation UI acceptance or model quality. | Preserve command result semantics, not facade return shape. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/application/test_analysis_service.py -q` | `49 passed`. | Legacy facade compatibility and direct replacement coverage remain green together. | Product runtime usage of facade; facade tests remain compatibility-only evidence. | Continue quarantining facade coverage until physical removal. |
| `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_evaluate_command_returns_typed_service_backed_summary tests/unit/backend/application/test_application_service.py::test_evaluate_and_clear_history_block_when_trainer_has_no_plan_history -q` | `2 passed`. | ApplicationService evaluation result and blocked-history behavior remain green after adding `training_active` diagnostics. | Full workflow acceptance. | Keep service-level tests focused on command-result contract. |
| `poetry run ruff check XBrainLab/backend/application/analysis_service.py tests/unit/backend/application/test_analysis_service.py` / `poetry run basedpyright XBrainLab/backend/application/analysis_service.py tests/unit/backend/application/test_analysis_service.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed command service and tests pass focused lint/type gates. | Full repo quality by itself. | Run broader gates before branch closure. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!`. | Product runtime and product-success test architecture guards remain clean after the replacement command-result slice. | Human Windows desktop acceptance. | Keep this gate in each backend/test hygiene slice. |

## 2026-05-12 Preprocess Operation Facade-Replacement Guard

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/backend/application/test_preprocess_service.py -q` | `5 passed`. | Preprocess command service directly covers individual notch, resample, normalize, and channel-reference mapping behavior previously represented by facade compatibility tests. | Full preprocessing workflow acceptance. | Keep command-service coverage as replacement when deleting facade wrappers. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/application/test_preprocess_service.py -q` | `48 passed`. | Legacy facade compatibility and direct replacement coverage remain green together. | Product runtime usage of facade; facade tests remain compatibility-only evidence. | Continue quarantining facade coverage until physical removal. |
| `poetry run ruff check tests/unit/backend/application/test_preprocess_service.py` / `poetry run basedpyright tests/unit/backend/application/test_preprocess_service.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed replacement tests pass focused lint/type gates. | Full repo quality by itself. | Run broader gates before branch closure. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!`. | Product runtime and product-success test architecture guards remain clean after the replacement test slice. | Human Windows desktop acceptance. | Keep this gate in each backend/test hygiene slice. |

## 2026-05-12 Data Compatibility Attach-Label Facade-Replacement Guard

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/backend/application/test_data_compatibility_service.py -q` | `7 passed`. | Data compatibility command service directly covers attach-label no-match, loader-error, full-data-path mapping, and multi-file batch behavior previously represented by facade compatibility tests. | Data Import UX acceptance or full external-label format coverage. | Keep command-service coverage as replacement when deleting facade wrappers. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/application/test_data_compatibility_service.py -q` | `50 passed`. | Legacy facade compatibility and direct replacement coverage remain green together. | Product runtime usage of facade; facade tests remain compatibility-only evidence. | Continue quarantining facade coverage until physical removal. |
| `poetry run ruff check tests/unit/backend/application/test_data_compatibility_service.py` / `poetry run basedpyright tests/unit/backend/application/test_data_compatibility_service.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed replacement tests pass focused lint/type gates. | Full repo quality by itself. | Run broader gates before branch closure. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!`. | Product runtime and product-success test architecture guards remain clean after the replacement test slice. | Human Windows desktop acceptance. | Keep this gate in each backend/test hygiene slice. |

## 2026-05-12 State Diagnostics Facade-Replacement Guard

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/backend/application/test_state_service.py -q` | `3 passed`. | State/query services directly carry raw/preprocessed runtime diagnostics and data-summary duplicate-channel diagnostics previously represented by facade compatibility tests. | Human UI diagnostics acceptance. | Preserve state/query diagnostics as replacement when deleting facade wrappers. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/application/test_state_service.py -q` | `46 passed`. | Legacy facade compatibility and direct replacement coverage remain green together. | Product runtime usage of facade; facade tests remain compatibility-only evidence. | Continue quarantining facade coverage until physical removal. |
| `poetry run ruff check tests/unit/backend/application/test_state_service.py` / `poetry run basedpyright tests/unit/backend/application/test_state_service.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed replacement tests pass focused lint/type gates. | Full repo quality by itself. | Run broader gates before branch closure. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!`. | Product runtime and product-success test architecture guards remain clean after the replacement test slice. | Human Windows desktop acceptance. | Keep this gate in each backend/test hygiene slice. |

## 2026-05-12 UI Accepted-Word Cleanup

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `rg -n "accepted" tests/unit/ui -g '*.py'` | No matches. | UI unit tests no longer contain broad `accepted` wording in comments/docstrings. | UI acceptance or behavioral coverage by itself. | Keep architecture guard examples separate from product/UI tests. |
| `rg -n "def test_.*(accepted|no_crash|does_not_crash)" tests/unit tests/integration -g '*.py'` | Only intentional architecture-compliance forbidden examples remain. | Weak UI/product test names are not present in the scanned suites. | Test quality beyond the naming pattern. | Continue relying on behavior assertions rather than names alone. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_montage_no_valid_config tests/unit/ui/test_ui_components.py::TestFilteringDialog::test_get_params_default -q` | `2 passed`. | The touched UI tests still pass after wording cleanup. | Broad UI acceptance. | No UX changes were made. |
| `poetry run ruff check tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/test_ui_components.py` / `poetry run basedpyright tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/test_ui_components.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Touched UI test files pass focused lint/type gates. | Full repo quality by itself. | Run broader gates before branch closure. |

## 2026-05-12 Backend/Test Hygiene Completion Audit

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `70 passed`. | Product-success tests do not bless `BackendFacade` or legacy fallback as product evidence, and architecture guard examples remain covered. | Runtime behavior outside scanned architecture rules. | Extend the guard when new product evidence paths are introduced. |
| `poetry run pytest --capture=sys tests/unit/backend/application -q` | `160 passed`. | Direct ApplicationService/command-service/query-service replacement coverage is green after the hygiene lane. | Product UI acceptance or full external dataset coverage. | Keep adding command-service tests for new backend behavior. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py tests/unit/backend/application/test_runtime.py tests/unit/backend/utils/test_montage_mapping.py -q` | `59 passed`. | Legacy facade compatibility remains quarantined and green beside direct replacement coverage. | Product runtime usage of facade or physical facade removal. | Delete facade compatibility tests only in a separate physical-removal slice. |
| Weak wording / weak-name scans | Weak wording scan has no matches; UI `accepted` scan has no matches; weak test-name scan only reports intentional architecture-compliance forbidden examples. | Weak UI/product test wording is cleaned into explicit behavior, command-route, or compatibility evidence. | Test quality beyond the scanned wording patterns. | Continue reviewing mock-heavy tests by behavior. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS with existing MkDocs Material advisory and nav notices / PASS. | Validation/worklog docs build and current diff has no whitespace errors. | Documentation content is automatically complete. | Keep validation records tied to executed commands. |

## 2026-05-12 Background Stabilization / Branch Readiness Audit

This pass kept UX work separate: no answer UI layout redesign and no Data Import UX redesign.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `70 passed`. | Product runtime and product-success architecture guards remain green. | Runtime behavior outside scanned guard scope. | Keep guard examples aligned with every new product adapter. |
| `poetry run pytest --capture=sys tests/unit/backend/application -q` | `160 passed`. | ApplicationService, command-service, query/state, and replacement backend coverage remain green. | Human desktop acceptance or complete external data coverage. | Keep adding direct command/service tests for new backend behavior. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py tests/unit/backend/application/test_runtime.py tests/unit/backend/utils/test_montage_mapping.py -q` | `59 passed`. | Legacy facade compatibility, shared service cache behavior, and extracted montage helper coverage are green. | Product runtime use of `BackendFacade`; these tests are compatibility-only evidence. | Physical facade removal should delete or migrate this cluster in a dedicated slice. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` | `31 passed, 8 warnings`. | Real-data IO integration remains green through current ApplicationService import coverage. | Warning-free MNE parsing or all external formats. | Warnings remain known MNE filename/annotation/CNT metadata/runtime notes. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q` | `2 passed`. | Representative tiny pipeline train/evaluate and study train-cycle smokes remain green. | Training quality, GPU acceptance, or full MVP workflow. | Keep as a small regression gate. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS with existing MkDocs Material advisory and nav notices / PASS after branch-readiness docs. | Docs build strictly and diff whitespace is clean. | Runtime behavior. | Re-run after future docs edits. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-12 22:51:43 UTC+08:00`. Includes ruff, basedpyright, architecture, startup smoke, UI baseline, UI dialog acceptance, UI unit suite, and real-data IO. | Fast engineering dashboard is green for this branch state. | Product complete, release approval, or human Windows acceptance. | Human-observable desktop smoke remains required before release claims. |
| `rg -n "BackendFacade\|backend\.facade" XBrainLab -g '*.py'` | Only `XBrainLab/backend/facade.py` and a montage-helper docstring mention remain. | Product package runtime has no direct `BackendFacade` import/instantiation outside the facade module itself. | Physical deletion readiness by itself. | Keep `BackendFacade` out of product packages while compatibility remains. |
| `rg -n "from XBrainLab\.backend\.facade\|BackendFacade\(" tests -g '*.py'` | References are confined to architecture guard examples, `test_facade_coverage.py`, `test_facade_headless.py`, and `application/test_runtime.py`. | Test usage is quarantined to guard/compatibility/runtime-cache evidence. | Product success through facade. | Delete or migrate the compatibility cluster when physically removing the facade. |

Branch / PR readiness:

- Scope completed: backend command-service replacement evidence, test hygiene, facade quarantine,
  non-UX validation gates, and current evidence docs.
- Intentionally not touched: answer UI layout, Data Import UX redesign, local LLM runtime,
  Windows human desktop acceptance, and signed packaging.
- Merge recommendation: this branch is suitable for review/merge as a backend/test hygiene and
  validation-readiness branch if the team accepts that physical `BackendFacade` removal is a later
  dedicated slice.
- Remaining risk: product runtime is guarded away from `BackendFacade`, but the facade file and its
  compatibility-only tests still exist. Human Windows desktop smoke is still required before product
  completion or release claims.

Superseded by the physical-removal slice below; the facade file and compatibility-only tests no
longer exist after that slice.

## 2026-05-12 Physical BackendFacade Removal

This slice kept UX work separate: no answer UI layout redesign and no Data Import UX redesign.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red gate: `poetry run python tests/architecture_compliance.py` after tightening the guard but before deleting facade files | Failed with 6 `BackendFacade` test-usage violations in `test_facade_coverage.py`, `test_facade_headless.py`, and `application/test_runtime.py`. | The guard now catches the old compatibility cluster before deletion. | Runtime correctness. | Delete/migrate the facade-only cluster, then re-run the guard. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `70 passed`. | Guard unit coverage covers forbidden product/runtime/test-side facade examples. | Product runtime behavior. | Keep examples when new adapters appear. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!`. | Product runtime, product-success tests, and unit tests no longer contain guarded facade usage. | Semantic proof outside scanned rules. | Keep this as a branch gate. |
| `poetry run pytest --capture=sys tests/unit/backend/application -q` | `159 passed`. | ApplicationService / command-service / state-query replacement coverage remains green after deleting the facade runtime case. | Human desktop acceptance or all external data combinations. | Keep direct command/service tests as the replacement surface. |
| `poetry run pytest --capture=sys tests/unit/backend/utils/test_montage_mapping.py tests/unit/test_architecture_compliance.py -q` | `77 passed`. | Montage fuzzy matching helper and architecture guard remain green without facade compatibility tests. | Human montage-dialog acceptance. | Keep helper tests; UI still owns confirmation. |
| `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py tests/unit/backend/application/test_runtime.py XBrainLab/backend/utils/montage_mapping.py` / focused `basedpyright` for the same implementation/test files | PASS / `0 errors, 0 warnings, 0 notes`. | Changed Python files are lint/type clean. | Full repo quality by itself. | Fast dashboard also ran below. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` | `31 passed, 8 warnings`. | Real-data IO remains green after physical facade removal. | Warning-free MNE parsing or all external formats. | Warnings remain known MNE filename/annotation/CNT metadata/runtime notes. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q` | `2 passed`. | Representative tiny pipeline train/evaluate and study train-cycle smokes remain green. | Training quality, GPU acceptance, or full MVP workflow. | Keep as a small regression gate. |
| `rg -n "from XBrainLab\.backend\.facade\|BackendFacade\(" XBrainLab -g '*.py'` / `rg --files XBrainLab/backend \| rg '/facade\.py$|^XBrainLab/backend/facade\.py$'` / `rg -n "facade_compatibility" pyproject.toml tests -g '*.py' -g '*.toml'` | No matches. | Product package no longer imports/constructs facade, the facade module file is gone, and no registered or test-side compatibility marker remains. | Docs/history references. | Keep architecture guard as the enforcement layer. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS with existing MkDocs Material advisory and nav notices / PASS after final docs edits. | Docs build strictly and diff whitespace is clean. | Runtime behavior. | Re-run after future docs edits. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-12 23:20:21 UTC+08:00`. Includes ruff, basedpyright, architecture, startup smoke, UI baseline, UI dialog acceptance, UI unit suite, and real-data IO. | Fast engineering dashboard is green after physical facade removal. | Product complete, release approval, or human Windows acceptance. | Human-observable desktop smoke remains required before release claims. |

## 2026-05-12 UI Controller Fallback Helper-Scope Guard

This slice kept UX work separate: no answer UI layout redesign and no Data Import UX redesign.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red gate: `poetry run python tests/architecture_compliance.py` after adding `check_ui_legacy_fallback_helper_scope()` | Failed with 33 direct `run_legacy_controller_fallback()` product-method violations. A follow-up red gate then caught 2 mutating legacy helper calls outside the explicit fallback gate. | The new guard caught real existing product-method fallback debt before implementation. | Runtime correctness by itself. | Keep adding concrete forbidden examples when new UI command routes appear. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `72 passed`. | Guard examples cover product-method direct fallback rejection and explicit legacy-helper allowance. | Semantic proof outside scanned rules. | Keep unit examples paired with every architecture rule. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!`. | Current product UI methods no longer directly call `run_legacy_controller_fallback()`, and product-success integration suites still do not bless legacy fallback / facade usage. | All controller reads or all read-only population paths are removed. | Continue auditing bootstrap/read-only controller paths separately. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/test_sidebars_and_components.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py tests/unit/ui/visualization/test_control_sidebar.py -q` | `220 passed`. | Focused UI command-route and legacy mock-context tests remain green after moving fallback calls into explicit helpers. | Human desktop acceptance or visual UX approval. | Keep broader UI evidence in the fast dashboard. |
| Focused `ruff check` / `basedpyright` for changed Python files | PASS / `0 errors, 0 warnings, 0 notes`. | Changed code and guard tests are lint/type clean. | Full repo quality by itself. | Fast dashboard also ran below. |
| `poetry run pytest --capture=sys tests/unit/backend/application -q` / `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` | `159 passed` / `8 passed`. | Backend ApplicationService and representative workflow coverage remain green after UI fallback isolation. | Human UI acceptance. | Keep command-service coverage as the backend contract. |
| `poetry run pytest --capture=sys tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q` | `2 passed`. | Representative pipeline train/evaluate and study train-cycle smokes remain green. | Training quality, GPU acceptance, or full MVP workflow. | Keep as a small regression gate. |
| `rg -n "run_legacy_controller_fallback\\(" XBrainLab/ui -g '*.py'` / `rg -n "get_legacy_controller_from_study\\|\\.get_controller\\(" XBrainLab/ui XBrainLab/llm XBrainLab/mcp -g '*.py'` / `rg -n "run_legacy_controller_fallback\\|get_legacy_controller_from_study\\|BackendFacade" tests/integration -g '*.py'` | Fallback calls are confined to `application_capabilities.py` and explicit legacy/fallback helpers; `get_controller()` is still present in MainWindow panel construction and explicit legacy bootstrap/read helpers; integration scan has no product-success fallback usage and only one `BackendFacade` UI transcript forbidden-string assertion. | Product-success tests no longer depend on controller fallback as success evidence. | Full zero-controller UI or removal of panel bootstrap controller injection. | Continue command-refresh/read-only controller path cleanup in later slices. |
| `git diff --check` / `poetry run mkdocs build --strict` | PASS / PASS with existing MkDocs Material advisory and nav notices. | Current diff has no whitespace errors and docs build strictly after canonical evidence updates. | Runtime behavior. | Re-run after docs edits when needed. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-12 23:59:02 UTC+08:00`. Includes full ruff, basedpyright, architecture, startup smoke, UI baseline, UI dialog acceptance, UI unit suite, and real-data IO. | Fast engineering dashboard is green after UI fallback helper-scope cleanup. | Product complete, release approval, or human Windows acceptance. | Human-observable desktop smoke remains required before release claims. |

## 常用 docs gate

```bash
poetry run mkdocs build --strict
git diff --check
```

如果改 CSS / layout，還要留下 built site screenshot 或可視覺審核 artifact。
