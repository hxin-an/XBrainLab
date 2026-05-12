# XBrainLab 驗證策略

最後更新：`2026-05-12`

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

- `artifacts/ui/data-import-wizard-steps/04-match-labels-final-loaded-label-files.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-final-many-labels.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-final-internal-events.png`

## Backend Test Hygiene Inventory

2026-05-11 compact inventory for the backend/test hygiene branch:

| Cluster | Classification | Current evidence | Action in this branch |
| --- | --- | --- | --- |
| Data Interpretation backend lifecycle | Strong behavior tests | `tests/unit/backend/application/test_data_interpretation_service.py` covers scan -> preview -> validate -> apply, external label sources, selected file scope, metadata apply, label import recipe state. `tests/integration/backend/test_application_service_workflow.py` covers non-mocked ApplicationService interpretation -> recipe reload -> dataset workflow. | Strengthened selected-scope and service apply coverage; added relative selected-file normalization coverage. |
| Scan / candidate / review / recipe contracts | Useful unit contract tests | `test_data_interpretation_scan.py`, `test_data_interpretation_candidate.py`, `test_data_interpretation_review.py`, `test_data_interpretation_recipe.py`, `test_data_interpretation_label_carriers.py`. | Preserves BIDS/file/folder scan behavior, selected scope, external label source provenance, structured action items, recipe reload/remap, label source mode, placement, duration, and class-map source. |
| Product runtime BackendFacade guard | Strong architecture guard | `tests/architecture_compliance.py` scans `XBrainLab/ui`, `XBrainLab/llm`, and `XBrainLab/mcp` for `BackendFacade` imports / construction, and scans product-success integration suites for `BackendFacade` workflow evidence. `tests/unit/test_architecture_compliance.py` covers forbidden runtime/test examples and allowed compatibility cases. | Product runtime packages and product-success tests must enter via `ApplicationService / Command API`; `BackendFacade` remains legacy compatibility only. |
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
| `poetry run pytest --capture=sys tests/unit/backend/utils/test_montage_mapping.py tests/unit/backend/test_facade_coverage.py -q` | `50 passed`. Full `test_facade_coverage.py` was red before fixing its helper because it created a mocked study but did not pass it into `BackendFacade`; after fixture correction the file is `43 passed`. | Montage fuzzy matching now has direct backend helper coverage outside `BackendFacade`, and facade compatibility tests actually exercise their mocked-study boundary. | Product runtime completion or human desktop acceptance. | Continue deleting or moving facade-only compatibility tests only after their command/service replacements are confirmed. |
| `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py tests/unit/backend/application/test_runtime.py tests/unit/backend/utils/test_montage_mapping.py -q` | `54 passed`. | Facade compatibility coverage, headless construction, shared service cache, and the extracted montage helper are mutually green after mocked-study fixture correction. | Product runtime usage of facade; architecture guard still treats facade as legacy-only. | Keep facade compatibility tests quarantined under unit tests until removal. |
| `poetry run ruff check XBrainLab/backend/utils/montage_mapping.py XBrainLab/backend/facade.py tests/unit/backend/utils/test_montage_mapping.py tests/unit/backend/test_facade_coverage.py` / `poetry run basedpyright XBrainLab/backend/utils/montage_mapping.py XBrainLab/backend/facade.py tests/unit/backend/utils/test_montage_mapping.py tests/unit/backend/test_facade_coverage.py` | PASS / `0 errors, 0 warnings, 0 notes`. | The montage helper, facade adapter, and compatibility tests pass focused lint/type gates. | Full repo health by itself. | Run broader dashboard only at branch closure or when product runtime scope changes. |
| `poetry run ruff check tests/unit/backend/test_facade_headless.py tests/unit/backend/application/test_runtime.py` / `poetry run basedpyright tests/unit/backend/test_facade_headless.py tests/unit/backend/application/test_runtime.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Headless facade compatibility and runtime cache tests pass focused lint/type gates. | Full repo health by itself. | Keep these tests as compatibility/runtime-only evidence. |
| `poetry run python tests/architecture_compliance.py` / `poetry run mkdocs build --strict` / `git diff --check` | `Architecture compliant!` / PASS with the existing MkDocs Material advisory / PASS. | Static architecture guard, docs build, and whitespace gate are clean for the montage-helper slice. | Human runtime acceptance or full repo dashboard health. | Continue with the next backend/test hygiene slice. |

## BackendFacade Compatibility Replacement Map

2026-05-12 status for eventual physical facade removal:

| Facade compatibility cluster | Current facade-only tests | Replacement coverage status | Removal note |
| --- | --- | --- | --- |
| Runtime construction / shared service cache | `tests/unit/backend/test_facade_headless.py`, `tests/unit/backend/application/test_runtime.py` | Covered for product runtime by `get_application_service(study)` tests, startup smoke, and architecture guard. | Remove with facade; keep `get_application_service` runtime tests. |
| Load data / attach labels / import labels | `TestLoadData`, `TestAttachLabels` in `test_facade_coverage.py` | Covered by `DataCompatibilityCommandService`, ApplicationService IO integration, and checked-in label-attached pipeline smokes. | Facade tests are compatibility-only. |
| Metadata / smart parse / remove files | Thin facade methods, broader UI/action tests | Covered by data table command tests and UI command-route tests. | No product reason to keep facade entry once legacy callers are gone. |
| Preprocess / epoch wrappers | `TestDelegation` preprocess methods | Covered by `PreprocessCommandService`, `ApplicationService`, UI command-route, and real-data pipeline smokes. | Facade wrapper tests can be deleted after compatibility removal. |
| Dataset generation / clear datasets | `TestGenerateDataset`, clear dataset tests | Covered by dataset generation service tests, ApplicationService workflow tests, and real-data pipeline smokes. | Keep service tests; do not preserve facade API as product evidence. |
| Training configure / start / stop / clear history | `test_backend_facade_headless`, `TestTrainingControl`, `TestDelegation` | Covered by training command service tests, ApplicationService tests, and pipeline smokes. | Facade tests only prove old method names. |
| Evaluate / visualize / saliency summaries | `TestGetLatestResults` and summary helpers | Covered by analysis command service and ApplicationService tests. | Preserve command result semantics, not facade shape. |
| Montage fuzzy matching | `TestSetMontage` in `test_facade_coverage.py` plus `tests/unit/backend/utils/test_montage_mapping.py` | Fuzzy cleanup now lives in `XBrainLab.backend.utils.montage_mapping` with direct helper tests. `BackendFacade.set_montage()` delegates to that helper before issuing `ApplyMontageCommand`; UI/dialog/tool paths still own interactive confirmation. | The highest-risk facade-specific logic is now outside the facade. Keep helper tests when deleting facade compatibility tests. |

Physical `BackendFacade` removal no longer depends on an unresolved montage fuzzy-matching decision.
It should still wait until remaining facade-only unit tests are either deleted as compatibility-only
or moved to command/service/dialog/helper tests.

## 常用 docs gate

```bash
poetry run mkdocs build --strict
git diff --check
```

如果改 CSS / layout，還要留下 built site screenshot 或可視覺審核 artifact。
