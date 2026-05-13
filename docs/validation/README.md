# XBrainLab 驗證策略

最後更新：`2026-05-14`

這頁說明 evidence 能證明什麼，也說明不能證明什麼。

## 快速讀法

先用這三步判讀 validation，不要從歷史 checkpoint 逐段倒推：

1. 看「Evidence 能力邊界」判斷某個綠燈能支撐什麼 claim。
2. 看「目前最可信的 gate」確認最近仍可引用的工程健康證據。
3. 看「最新證據導覽」決定要追哪個 checkpoint；只有需要細節時才往下讀日期記錄。

## 目前最可信的 gate

| Gate | 最近可信結果 | 用途 | 不能取代 |
| --- | --- | --- | --- |
| Fast quality dashboard | 2026-05-14 00:11:43 UTC+08:00 `PASS` | lint、type、architecture guard、startup smoke、UI baseline/dialog/unit、real-data IO 的快速健康檢查。 | product complete、human Windows acceptance、long local-model session。 |
| Architecture compliance | 最近 checkpoint `Architecture compliant!`，guard unit `97 passed` | 阻擋已知 `BackendFacade`、legacy fallback、direct state、positive controller lookup、docs overclaim、weak protocol/string evidence 等 regression。 | runtime semantic proof for every possible path。 |
| Focused UI integration | `test_ui_refresh.py`、`test_ui_integration.py`、`test_panel_controller_binding.py` -> `8 passed` | MainWindow launch/navigation/tab-refresh 和 injected controller event wiring 不再把 legacy lookup 當成功證據。 | full zero-controller UI 或人工桌面驗收。 |
| Product smokes / real tools | guarded UI product smokes、epoch runtime、real-tools suites recently PASS | product evidence 轉向 `QueryStateCommand` / command diagnostics / UI-visible state。 | 所有 integration tests 都已清成 product evidence。 |
| `mkdocs build --strict` | 最近 checkpoint PASS | 文件站可建且連結/nav 基本有效。 | 文件內容一定正確或容易讀。 |

## 最新證據導覽

下表是讀這頁的索引，不是新的 claim。每一列都指向下方可追溯的 checkpoint 或 gap section。

| 你要判斷 | 先看 | 可以支持 | 不能支持 |
| --- | --- | --- | --- |
| MCP / headless status 是否仍走 command state | [MCP direct Study-state guard](#2026-05-13-mcp-direct-study-state-guard-checkpoint) 和 [MCP HTTP progress command-state](#2026-05-13-mcp-http-progress-command-state-checkpoint) | MCP progress/status 不回到 direct mutable `Study` read 或 controller lookup bypass。 | full external MCP client certification。 |
| MCP stdio / HTTP tests 是否仍只證明有 response | [MCP JSON-RPC exact evidence](#2026-05-14-mcp-json-rpc-exact-evidence-checkpoint) | MCP tests 檢查 JSON-RPC envelope、request id、error/result separation、tool schema、structuredContent、adapter session、command name 和 accepted/status。 | external MCP client certification、remote security review、or long-running job durability。 |
| Agent pipeline stage prompt / label tests 是否仍只看 non-empty | [Agent pipeline-state exact prompt evidence](#2026-05-14-agent-pipeline-state-exact-prompt-evidence-checkpoint) | Stage config tests 檢查每個 stage 的 prompt markers、action/blocked guidance、exact label map，且 architecture guard 擋回 generic non-empty string assertion。 | local-model session quality、tool-call benchmark accuracy、or assistant UX acceptance。 |
| LLM parser tests 是否仍只看 parsed object exists | [LLM parser exact parse-result evidence](#2026-05-14-llm-parser-exact-parse-result-evidence-checkpoint) | Parser tests 檢查 exact `(tool_name, parameters)` list，且 architecture guard 擋回 generic `parsed/result is not None`。 | Full local-model parsing quality、tool-call benchmark accuracy、or assistant UX acceptance。 |
| LLM tool/debug tests 是否仍只看 registry 非空 | [LLM tool/debug exact registry evidence](#2026-05-14-llm-tooldebug-exact-registry-evidence-checkpoint) | Tool/debug tests 檢查 exact agent tool-name set、backend resolver class identity、debug calls 和 visualization figure type。 | Full agent runtime acceptance or local-model behavior。 |
| UI controller hit 是否仍代表 product legacy path | [UI controller exception-map readability checkpoint](#2026-05-14-ui-controller-exception-map-readability-checkpoint)、[UI bridge fallback cleanup](#2026-05-14-ui-training-bridge-fallback-cleanup-checkpoint)、[controller.study lookup guard](#2026-05-14-controllerstudy-lookup-guard-checkpoint) 和 [UI 目前架構](../architecture/ui.md) | Source 對照表區分 panel bootstrap、mock fallback、readonly render fallback、refresh surface、assistant adapter 和 lower-level domain object；Evaluation / Visualization training-event bridge 不再 fallback lookup training controller，guard 也不允許把 `controller.study.get_controller()` 藏在 legacy helper。 | Full zero-controller UI、human desktop acceptance、or runtime proof for every panel state。 |
| UI navigation refresh 測試是否仍靠 mock call / 猜 index | [UI refresh duplicate-test cleanup](#2026-05-14-ui-refresh-duplicate-test-cleanup-checkpoint) | 重複的 mock-heavy integration test 已移除；replacement coverage 檢查 exact `switch_page()` coordinator delegation、target-panel scope、navigation checked state、command/observer refresh routing。 | Human UI acceptance 或每個 panel render content。 |
| Headless UI smoke 是否仍只看 object exists | [Headless UI exact state evidence](#2026-05-14-headless-ui-exact-state-evidence-checkpoint) | `test_ui_headless.py` now checks MainWindow class, exact nav labels/check state, exact page switch state, and exact empty `QueryStateCommand(data_summary)` diagnostics. | Human Windows desktop acceptance, visual UX, or loaded-data workflow. |
| pytest-qt UI integration 是否仍只看 widget exists / tab count >= | [pytest-qt UI exact contract evidence](#2026-05-14-pytest-qt-ui-exact-contract-evidence-checkpoint) | `test_e2e_qtbot.py` now checks exact navigation checked-state transitions, AI button contract, stack panel order/types, Evaluation/Visualization tab labels, and product InfoPanelService wiring. | Human UX approval, screenshot quality, or full data workflow. |
| Real UI tools smoke 是否仍靠 substring / non-`None` | [Real-tools UI exact state evidence](#2026-05-14-real-tools-ui-exact-state-evidence-checkpoint) | `test_real_tools_e2e.py` now uses deterministic FIF data and checks exact list/load/info/preprocess/config/UI messages plus exact ApplicationService state deltas. | Full agent benchmark, training quality, or human UI acceptance. |
| Evaluation panel 是否還會顯示 stale metrics | [Evaluation display command evidence](#2026-05-13-evaluation-display-command-evidence-checkpoint) | service-owned average metrics 缺失時清空 stale display。 | human evaluation UX acceptance。 |
| Data Import runtime / agent-MCP schema 是否仍可引用 | [Data Import runtime integration](#2026-05-13-data-import-runtime-integration-checkpoint) | command/service/dialog contracts 和 agent/MCP baseline。 | final Match Labels / Review and Import UX。 |
| 測試是否能擋 facade / legacy fallback 回流 | [Backend test hygiene inventory](#backend-test-hygiene-inventory) 和 architecture guard checkpoints | 已知 forbidden product-success evidence 被 guard。 | semantic proof for every lower-level test。 |
| Real-data IO 測試是否仍只證明 no-crash | [Real-Data IO shape-evidence](#2026-05-13-real-data-io-shape-evidence-checkpoint) | compact/public EEG fixtures 會檢查 loaded data 維度、非空內容、channel axis 對齊，以及 command import summary。 | scientific reproducibility、all possible external formats、or human Data Import acceptance。 |
| Metadata pipeline 測試是否仍靠 random label / generic assertion | [Metadata real-data event evidence](#2026-05-13-metadata-real-data-event-evidence-checkpoint) | A01T metadata test 會檢查 raw shape、fixed filename parse、deterministic label round-trip、event shape、onset alignment 和 final event IDs。 | Data Import UX acceptance、all external label heuristics、or scientific validation。 |
| Real-data pipeline smoke 是否仍只看 non-empty | [A01T real-data pipeline exact evidence](#2026-05-13-a01t-real-data-pipeline-exact-evidence-checkpoint) | A01T command-spine smoke 現在檢查 exact event names / ids、epoch shape、trial split summary 和 one-run training history。 | Training quality、all external datasets、or human desktop acceptance。 |
| Checked-in GDF+MAT training smoke 是否仍只看 non-empty | [Checked-in GDF+MAT exact evidence](#2026-05-13-checked-in-gdfmat-exact-evidence-checkpoint) | A01T/A02T/A03T label-attached smokes 現在檢查 exact label events、epoch counts、trial split summaries 和 one-row training history。 | Scientific claim、all subjects/formats、or long training quality。 |
| Public cross-source training smoke 是否只證明 no-crash | [Public cross-source command evidence](#2026-05-13-public-cross-source-command-evidence-checkpoint) | EDF/GDF/SET/CNT smokes 檢查 fixture event mapping、epoch count 與 split total 對齊、one-run training history。 | Training quality、full format certification、or human desktop acceptance。 |
| ApplicationService workflow split 是否仍只看 non-empty | [ApplicationService exact split evidence](#2026-05-13-applicationservice-exact-split-evidence-checkpoint) | Core command-spine workflow 現在檢查 synthetic split summary 含 train/val/test count 與 audit payload。 | UI refresh acceptance、real-data breadth、or human desktop acceptance。 |
| Real-tool chain 是否仍只看 dataset count | [Real-tool chain exact evidence](#2026-05-13-real-tool-chain-exact-evidence-checkpoint) | LLM real-tool A01T chain 現在檢查 exact epoch state、dataset split summary、tool result string 和 one-run training state。 | Tool-call benchmark accuracy、human assistant UX、or long local-model session。 |
| UI product walkthrough 是否仍只看 dataset count | [UI product walkthrough exact-state evidence](#2026-05-13-ui-product-walkthrough-exact-state-evidence-checkpoint) | Offscreen user-facing walkthrough 現在檢查 exact epoch state 與 dataset split summary，而不是只看 dataset count。 | 不能支持 Human Windows desktop acceptance、visual UX approval、or 完整零 controller UI。 |
| Data Interpretation label semantics 是否只是 preview 假資料 | [Data Interpretation label-semantics backend evidence](#2026-05-14-data-interpretation-label-semantics-backend-evidence-checkpoint) | reviewed event-code label files、interval end/stop/offset duration、run-dependent internal event mapping、recipe/state snapshot preservation 有 backend contract tests。 | Final Match Labels UX approval、all EEG label semantics、or human Data Import acceptance。 |
| artifacts 是否仍是重複 evidence dump | [Artifact current-tree cleanup](#2026-05-13-artifact-current-tree-cleanup-checkpoint) | current tree 移除被 full dashboard / consolidated walkthrough / canonical wizard screenshots 覆蓋的短版或探索型 artifact。 | 不能支持 runtime correctness、human acceptance、or product completion。 |
| Lower-level preprocess controller 測試是否仍只是 non-`None` | [Preprocess controller shape/event evidence](#2026-05-13-preprocess-controller-shapeevent-evidence-checkpoint) | Controller integration tests 會檢查 `Raw` object、signal/epoch shape、filter shape preservation、selected event code 和 reset history。 | Product command-spine success、UI refresh acceptance、or zero-controller UI architecture。 |
| Synthetic preprocess validation 是否仍靠 random/no-crash | [Preprocess validation deterministic evidence](#2026-05-13-preprocess-validation-deterministic-evidence-checkpoint) | Synthetic preprocess tests now use a fixed fixture and assert resample event codes, epoch shape, operation history, and reset shape. | Real-data product acceptance、UI responsiveness、or all preprocess edge cases。 |
| AgentManager montage 測試是否仍靠 `Study.epoch_data` side effect | [AgentManager montage command evidence](#2026-05-13-agentmanager-montage-command-evidence-checkpoint) | Montage picker 的 channel source 來自 `QueryStateCommand`，apply payload 以 `ApplyMontageCommand` 檢查 channels / positions / montage name。 | 不能支持 Human montage UX acceptance 或完整零 controller UI。 |
| 能不能宣稱桌面 MVP 人工驗收 | [Human Windows Desktop Acceptance Gap](#human-windows-desktop-acceptance-gap) | 尚缺哪些 click-through / artifact。 | release approval。 |

## Evidence 能力邊界

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

## 2026-05-14 UI Controller Exception-Map Readability Checkpoint

This docs/readability slice did not change runtime behavior. It updated
`docs/architecture/ui.md` so the remaining UI/controller hits are interpreted from source instead
of being flattened into a single "legacy exists" claim. The page now separates panel constructor
adapters, mock/legacy fallback gates, readonly display fallback, refresh surfaces, assistant UI
adapters, lower-level domain-object presentation, and state-snapshot language.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Source audit: controller/fallback/refresh symbol scan over `XBrainLab/ui` plus guard constants in `tests/architecture_compliance.py` | Confirmed the remaining hits are covered by the documented categories. | The architecture doc now gives a readable map for interpreting current controller exceptions. | Runtime behavior by itself, full zero-controller UI, or human desktop acceptance. | Keep the map updated whenever a fallback helper is removed or a new exception category appears. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `97 passed`. | Existing architecture guards still reject known product-success fallback, controller lookup, direct state, stale render, and docs-overclaim patterns after the docs update. | Semantic proof for every panel state or every lower-level component test. | Add guard examples only when a new regression pattern is found. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS. | Docs site builds and the docs-only diff is whitespace clean. | Content correctness without source review. | Pair future docs claims with source or runtime evidence. |

## 2026-05-14 UI Training Bridge Fallback Cleanup Checkpoint

This refactor slice removed the remaining Evaluation / Visualization training-event bridge path
that reached from a panel controller back into `controller.study.get_controller("training")`.
Product `MainWindow` already injects the training controller when it constructs those panels; mock
or standalone contexts without that injection now simply skip the training lifecycle bridge instead
of performing a legacy lookup.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_panel_event_bridges.py tests/unit/ui/test_panel_constructor_boundaries.py -q` | `23 passed`. | Injected Evaluation / Visualization training bridges still refresh on lifecycle events, and missing injected controllers do not call back into `study.get_controller`. | Full UI refresh acceptance or every panel display path. | Continue moving remaining constructor adapters toward view-model/service inputs. |
| `rg -n "study.get_controller\\(\"training\"\\)" XBrainLab/ui/panels/evaluation/panel.py XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_panel_event_bridges.py` | No source matches in the two product panel files. | The removed bridge fallback no longer exists in Evaluation / Visualization panel source. | Absence of every possible UI controller dependency. | Keep broader UI controller scans in architecture review. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `97 passed`. | The refactor did not weaken existing architecture guards. | Runtime semantic proof for all UI paths. | Add a guard only if a future direct bridge lookup pattern reappears. |
| Focused `ruff check` / `basedpyright` on changed UI/test files, plus `poetry run mkdocs build --strict` and `git diff --check` | PASS. | Changed Python files are lint/type clean, docs build, and diff is whitespace clean. | Human Windows desktop acceptance. | Pair with product-smoke only when changing visible UI behavior. |

## 2026-05-14 Controller.study Lookup Guard Checkpoint

This guard slice did not change runtime behavior. It tightened
`check_ui_controller_study_get_controller_fallbacks(...)` so UI code may not call
`controller.study.get_controller(...)` even from a function named `_legacy_*` or `*fallback*`.
That turns the removed Evaluation / Visualization training-bridge fallback into a regression
guard instead of relying on source review alone.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `97 passed` / `Architecture compliant!`. | Architecture guard now rejects `controller.study.get_controller(...)` hidden behind a legacy helper while current UI source stays compliant. | Full zero-controller UI. | If a real compatibility need appears, route it through named bootstrap or service-backed injection instead of direct controller.study lookup. |
| `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py` / `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py` | PASS / PASS. | Changed architecture guard files are lint/type clean. | Runtime behavior by itself. | Keep guard messages actionable. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS. | Docs build and the guard diff is whitespace clean. | Human desktop acceptance. | Keep validation wording scoped to architecture regression protection. |

## 2026-05-14 UI Refresh Duplicate-Test Cleanup Checkpoint

This test-cleanup slice removed `tests/integration/ui/test_ui_refresh.py`, a mock-heavy
integration test that patched all five panel classes and asserted generic `update_panel()` calls
while carrying obsolete comments about guessed tab indexes. The replacement coverage is stronger
and already lives in focused UI unit tests: `test_main_window_sync.py` checks exact
`switch_page()` -> `refresh_after_navigation(...)` delegation, target-panel refresh scope, and nav
button checked state; `test_refresh_coordinator.py` checks command, navigation, and observer
refresh routing.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_main_window_sync.py tests/unit/ui/test_refresh_coordinator.py -q` | `38 passed`. | Replacement tests cover exact MainWindow navigation delegation and refresh coordinator scope without relying on the deleted weak integration test. | Human UI acceptance or visible panel content correctness. | Keep UI refresh claims tied to coordinator/state evidence, not generic mock calls. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `97 passed`. | Removing the duplicate test did not weaken architecture guard coverage. | Semantic proof for every UI refresh path. | Add guard coverage only for new regression patterns. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS. | Docs remain buildable and deletion diff is whitespace clean. | Runtime behavior. | Keep deleted weak tests documented when replacement coverage matters. |

## 2026-05-14 Headless UI Exact State Evidence Checkpoint

This test-quality slice tightened `tests/integration/ui/test_ui_headless.py` so the headless UI
smoke no longer passes because the fixture and study merely exist. The test now asserts the product
`MainWindow` type, exact five-panel navigation labels, checked-state transitions for Dataset ->
Preprocess -> Training, and exact empty `QueryStateCommand(data_summary)` diagnostics from
`ApplicationService`.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/integration/ui/test_ui_headless.py -q` | `3 passed`. | Headless MainWindow smoke has exact navigation and command-state assertions instead of object-existence checks. | Human Windows desktop acceptance, screenshot quality, or real loaded-data workflow. | Extend only with user-visible state assertions, not generic object checks. |
| Focused `ruff check` / `basedpyright` on the changed test file | PASS / PASS. | The tightened UI smoke is lint/type clean. | Runtime behavior beyond the tested smoke. | Keep exact expected diagnostics synchronized with `ApplicationService` state contract. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run mkdocs build --strict` / `git diff --check` | `Architecture compliant!` / `97 passed` / PASS / PASS. | The test-evidence change did not weaken architecture or docs gates. | Product completion. | Re-run dashboard only when broader artifact refresh is intended. |

## 2026-05-14 pytest-qt UI Exact Contract Evidence Checkpoint

This test-quality slice tightened `tests/integration/ui/test_e2e_qtbot.py`. The test no longer
passes because key widgets merely exist or because Evaluation / Visualization have "enough" tabs.
It now asserts exact top-nav labels and checked-state transitions, exact AI button text/object
contract, exact stacked-panel order and classes, exact Evaluation / Visualization tab labels, and
the product `InfoPanelService` wiring used by `MainWindow`.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/integration/ui/test_e2e_qtbot.py -q` | `17 passed`. | pytest-qt UI integration checks exact visible navigation/panel/dock/service contract instead of object existence or loose counts. | Human Windows desktop acceptance, final UX approval, or real data workflow. | Add screenshot or human evidence separately when visual quality is in scope. |
| `poetry run ruff check tests/integration/ui/test_e2e_qtbot.py` / `poetry run basedpyright tests/integration/ui/test_e2e_qtbot.py` | PASS / PASS. | Tightened test file is lint/type clean. | Runtime behavior outside this UI contract slice. | Keep expected labels synchronized with intentional UI copy changes. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run mkdocs build --strict` / `git diff --check` | `Architecture compliant!` / `97 passed` / PASS / PASS. | The test-evidence change did not weaken architecture or docs gates. | Product completion. | Re-run dashboard only for broader checkpoint validation. |

## 2026-05-14 Real-Tools UI Exact State Evidence Checkpoint

This test-quality slice tightened `tests/integration/ui/test_real_tools_e2e.py`. The test now
uses deterministic synthetic FIF input and checks exact real-tool messages plus ApplicationService
state for raw file metadata, data-list counts/files, model selection, training configuration, and
UI panel-switch request formatting. It no longer relies on substring checks or
`training_option is not None`.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/integration/ui/test_real_tools_e2e.py -q` | `1 passed`. | Real UI tool chain evidence checks deterministic data and exact command-state deltas through ApplicationService. | Tool-call benchmark accuracy, training quality, or human UI acceptance. | Keep real-tool string contracts aligned with structured command result semantics. |
| `poetry run ruff check tests/integration/ui/test_real_tools_e2e.py` / `poetry run basedpyright tests/integration/ui/test_real_tools_e2e.py` | PASS / PASS. | Tightened real-tools UI smoke is lint/type clean. | Runtime breadth beyond this single synthetic FIF workflow. | Add representative real-data cases separately. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run mkdocs build --strict` / `git diff --check` | `Architecture compliant!` / `97 passed` / PASS / PASS. | The test-evidence change did not weaken architecture or docs gates. | Product completion. | Re-run dashboard only for broader checkpoint validation. |

## 2026-05-14 Agent Pipeline-State Exact Prompt Evidence Checkpoint

This test-quality slice did not change agent runtime behavior. It tightened
`tests/unit/llm/test_pipeline_state.py` so stage configuration no longer passes because
`system_prompt` or `PipelineStage.label` is merely non-empty. The tests now assert exact
stage-label display text and stage-specific prompt markers for Data Interpretation entry,
preprocessing, dataset generation, training readiness, locked training, and trained-analysis
guidance. Architecture compliance now rejects generic non-empty string assertions in this file.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py -q` | `25 passed` | Pipeline stage tests check exact labels and prompt contract markers instead of generic non-empty strings. | Assistant UX acceptance, local-model quality, or tool-call benchmark accuracy. | Keep prompt checks tied to workflow guidance, not incidental wording. |
| Weak-evidence scan: `rg -n "assert .* is not None\|len\\(.+\\) > 0\|non-empty\|no crash\|no_crash\|does_not_crash" tests/unit/llm/test_pipeline_state.py` | No matches. | The targeted pipeline-state test file no longer contains the scanned weak assertion patterns. | Full LLM test-suite quality. | Continue case-by-case cleanup where stronger behavior evidence exists. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `95 passed` / `Architecture compliant!` | Architecture guard now rejects generic non-empty pipeline-state string assertions while allowing exact prompt/label contracts. | Semantic proof for every LLM test file. | Extend only after targeted files have replacement exact evidence. |
| `poetry run ruff check tests/unit/llm/test_pipeline_state.py tests/architecture_compliance.py tests/unit/test_architecture_compliance.py` / `poetry run basedpyright tests/unit/llm/test_pipeline_state.py tests/architecture_compliance.py tests/unit/test_architecture_compliance.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed test and guard files are lint and type clean. | Runtime behavior by itself. | Pair static checks with focused behavior tests. |

## 2026-05-14 LLM Parser Exact Parse-Result Evidence Checkpoint

This test-quality slice did not change parser runtime behavior. It tightened
`tests/unit/llm/test_parser.py` and adjacent parser return-path coverage in
`tests/unit/llm/test_misc_coverage.py` so valid JSON / alias / relaxed-code-block parser cases no
longer pass because `CommandParser.parse(...)` returned a non-`None` object. The tests now assert
the exact parsed `(tool_name, parameters)` list. Architecture compliance now rejects generic
non-`None` parser assertions in these files.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/llm/test_misc_coverage.py tests/unit/llm/test_parser.py -q` | `25 passed` | Parser tests and parser return-path coverage assert exact command/parameter output for valid command shapes instead of object existence. | Full local-model parsing quality, tool-call benchmark accuracy, or assistant UX acceptance. | Keep additional parser cleanup tied to exact accepted/rejected shapes. |
| Weak-evidence scan: `rg -n "assert .* is not None\|len\\(.+\\) > 0\|len\\(.+\\) >= 1\|non-empty\|no crash\|no_crash\|does_not_crash" tests/unit/llm/test_parser.py tests/unit/llm/test_misc_coverage.py` | No matches. | The targeted parser test files no longer contain the scanned weak assertion patterns. | Full LLM parser coverage. | Continue only where stronger exact parse expectations are available. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `97 passed` / `Architecture compliant!` | Architecture guard now rejects generic non-`None` parser assertions while allowing exact parse-result contracts. | Semantic proof for every LLM test file. | Extend guards narrowly after exact replacements exist. |
| `poetry run ruff check tests/unit/llm/test_parser.py tests/architecture_compliance.py tests/unit/test_architecture_compliance.py` / `poetry run basedpyright tests/unit/llm/test_parser.py tests/architecture_compliance.py tests/unit/test_architecture_compliance.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed parser test and guard files are lint and type clean. | Runtime behavior by itself. | Pair static checks with focused behavior tests. |

## 2026-05-14 LLM Tool/Debug Exact Registry Evidence Checkpoint

This test-quality slice did not change runtime behavior. It tightened
`tests/unit/llm/test_tools_and_debug.py` and the duplicate coverage companion so tool registry,
backend resolver, debug script, and visualization checks no longer pass because collections or
objects merely exist. They now assert the exact prompt-facing agent tool-name set, exact backend
model/preprocessor class identity, exact debug tool-call dataclass output, and Matplotlib
`Figure` type after failed base visualization rendering.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py -q` | `52 passed` | Tool/debug coverage asserts exact tool registry and backend/debug/visualization contracts instead of non-empty or non-`None` checks. | Full agent runtime acceptance or local-model behavior. | Decide later whether the duplicate `_cov` file should be consolidated after replacement coverage is stable. |
| Weak-evidence scan: `rg -n "assert .* is not None\|len\\(.+\\) > 0\|non-empty\|no crash\|no_crash\|does_not_crash" tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py` | No matches. | The targeted tool/debug test files no longer contain the scanned weak assertion patterns. | Full LLM test-suite quality. | Continue replacing weak assertions only with stronger behavior or exact contract checks. |
| `poetry run ruff check tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py` / `poetry run basedpyright tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed tool/debug test files are lint and type clean. | Runtime behavior by itself. | Pair static checks with focused behavior tests. |

## 2026-05-14 MCP JSON-RPC Exact Evidence Checkpoint

This test-quality slice did not change MCP runtime behavior. It tightened MCP stdio / HTTP
adapter evidence so tests no longer treat a non-`None` response as product success. The focused
tests now assert the JSON-RPC envelope, request id, error/result separation, tool schema,
structured command content, adapter session metadata, command name, `accepted`, and command result
status.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/mcp/test_server.py tests/unit/mcp/test_http_server.py tests/integration/mcp/test_stdio_server.py -q` | `15 passed` | MCP stdio / HTTP baseline tests assert protocol and command-result shape instead of generic response existence. | External MCP client certification, remote security review, or durable long-running job persistence. | Keep exact JSON-RPC assertions when new MCP tools or job APIs are added. |
| Weak-evidence scan: `rg -n "assert .* is not None\|len\\(.+\\) > 0\|non-empty\|no crash\|no_crash\|does_not_crash" tests/unit/mcp/test_server.py tests/unit/mcp/test_http_server.py tests/integration/mcp -g '*.py'` | No matches in the focused MCP stdio / HTTP evidence set. | The targeted MCP tests no longer contain the scanned weak assertion patterns. | Full test-suite quality; this scan is pattern-based and not semantic proof for every assertion. | Continue replacing weak assertions only when stronger behavior evidence is available. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `93 passed` / `Architecture compliant!` | Architecture guard now rejects generic non-`None` MCP response assertions in `tests/unit/mcp` and `tests/integration/mcp`, while allowing exact JSON-RPC shape assertions. | Semantic proof for every MCP assertion or external MCP client behavior. | Add concrete guard examples when new MCP evidence patterns appear. |
| `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_server.py` / `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_server.py` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed MCP and architecture guard files are lint and type clean. | Runtime behavior by itself. | Pair lint/type checks with focused behavior tests. |

## 2026-05-14 Data Interpretation Label-Semantics Backend Evidence Checkpoint

This backend/test slice did not redesign Match Labels, Review and Import, or any Data Import
layout. It strengthened the Data Interpretation contract behind already-reviewed choices:
event-code placement can apply label rows to matching EEG event codes in original event order,
interval placement can honor selected `end` / `stop` / `offset` columns as duration boundaries,
and PhysioNet-style `T1` / `T2` internal events are flagged as run-dependent semantics that need a
confirmable run mapping before supervised training claims are trustworthy. The mapping now survives
candidate state, applied interpretation, recipe save/reload choices, and state snapshots.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Initial focused red run: `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_recipe.py -q` | Failed 3 cases before fixes: event-code output order, interval duration floating tail, and `S001R04` run token parsing. | New tests exercised real backend contract gaps instead of only screenshot / preview assumptions. | Runtime correctness after failure. | Keep red-to-green evidence when adding Data Interpretation semantics. |
| `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_recipe.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_data_interpretation_state.py tests/unit/backend/load_data/test_label_loader.py tests/unit/backend/load_data/test_label_loader_coverage.py -q` | `115 passed` | Event-code label apply, interval end-field duration handling, run-dependent event mapping preservation, state snapshot propagation, and label-loader compatibility are covered by focused backend tests. | Final Match Labels UX approval, all possible carrier schemas, human Data Import acceptance, or scientific validation. | Add UI-visible evidence only when UX work is explicitly in scope. |
| Expanded backend unit run: `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_data_interpretation_*.py tests/unit/backend/load_data/test_label_loader.py tests/unit/backend/load_data/test_label_loader_coverage.py -q` | `142 passed` | The new label-semantics contract stays green with the rest of the Data Interpretation backend unit suite. | Real-data breadth or human Data Import acceptance. | Pair with real-data/product smoke only when changing runtime source scanning or visible UI flow. |
| Focused `ruff check` / `ruff format --check` / `basedpyright` on changed backend/test files | PASS / PASS / `0 errors, 0 warnings, 0 notes`. | Changed backend/test slice is lint, format, and type clean. | Product runtime evidence by itself. | Keep type checks paired with behavior tests for backend contract changes. |
| `poetry run mkdocs build --strict` | PASS. | Docs site still builds after current/validation checkpoint updates. | Content correctness or runtime behavior by itself. | Keep Match Labels UX claims out of backend-only evidence. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `git diff --check` | `Architecture compliant!` / `91 passed` / PASS. | The label-semantics backend slice and docs checkpoint did not weaken current architecture / docs overclaim guards and the diff is whitespace clean. | Full product architecture completion. | Re-run dashboard only when a broader integration checkpoint is needed. |

## 2026-05-13 Artifact Current-Tree Cleanup Checkpoint

This docs/artifact hygiene slice did not change runtime behavior or UX. It reduced current-tree
artifact duplication by removing short, affected-case, guardrail-only, exploratory, or superseded
artifact families while keeping the current evidence entrances: quality dashboard, full
deterministic / primary / fallback evals, Data Import wizard screenshots, consolidated human-like
walkthrough, MCP / launcher evidence, local ChatPanel pipeline/training walkthroughs, visualization
render evidence, docs-site visual check, and Data Interpretation capability evidence.

Removed artifact families remain recoverable from git history; they are not new negative evidence.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `git ls-files artifacts` / duplicate-hash audit / canonical-doc reference scan | Removed obsolete current-tree copies of `agent_evals/deterministic_changed`, `agent_evals/local_*_analysis_tools`, `agent_evals/local_*_guardrail_smoke`, `ui/chatpanel-local-workflow`, `ui/chatpanel-local-training-readiness`, `ui/data-source-entry-options`, `ui/smart-parser`, and legacy `ui/data-interpretation-*` replay files. Current canonical docs had no direct dependency on those deleted paths. | Artifact tree is easier to navigate and no longer keeps redundant historical slices as if they were current truth. | Runtime behavior, product completion, human Windows acceptance, or evidence validity for retained artifacts. | Keep future artifacts behind `artifacts/README.md` retention rules; do not create new screenshot families without an evidence purpose. |
| `du -sh artifacts` after cleanup | `9.4M` current artifact tree. | Current evidence tree is smaller after duplicate/superseded family removal. | Repository size history or artifact generator output size. | Re-run generators only when the evidence itself changes, not just to fill deleted historical directories. |
| `poetry run mkdocs build --strict` | PASS. | Docs site still builds strictly after artifact link/readability cleanup. | Runtime behavior or human acceptance. | Keep artifact paths in current docs limited to retained evidence entrances. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed`. | Artifact cleanup wording did not weaken current architecture / docs overclaim guards. | Semantic proof for every retained artifact. | Continue pairing artifact pruning with claim-boundary docs. |
| `git diff --check` / `git diff --cached --check` | PASS / PASS. | Working and staged diffs are whitespace clean. | Content correctness by itself. | Keep running both checks when using staged file removals plus unstaged docs edits. |

## 2026-05-14 Artifact Current-Tree Second-Pass Cleanup Checkpoint

This artifact hygiene slice did not change runtime behavior, backend semantics, or Data Import UX.
It removed stale or duplicate evidence entrances from the current tree while preserving canonical
evidence: root deterministic eval output, local primary/fallback model reports, the consolidated
human-like walkthrough, MCP / launcher / visualization evidence, docs-site visual evidence, and a
minimal Data Import wizard screenshot set.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Artifact reference audit over current docs and artifact indexes | Removed stale `agent_evals/deterministic/latest.md`, short `ui/training-start-confirmation/` replay artifacts, and extra Data Import wizard status variants. | Current artifact tree no longer presents duplicate/stale evidence as current truth. | Runtime correctness, product completion, human Windows acceptance, or final Data Import UX approval. | Keep new screenshots behind `artifacts/README.md` retention rules. |
| Data Import wizard retained set review | Retained one canonical screenshot per wizard step plus four Match Labels placement panels. | A reader can still inspect the current wizard flow without sorting through repeated status variants. | Full UX approval or exhaustive screenshot coverage for every wizard state. | Regenerate variants only for a targeted UX review and prune them after the review. |
| `poetry run mkdocs build --strict` / `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | PASS / `Architecture compliant!` / `93 passed`. | Canonical docs still build strictly and architecture/doc guards stay green after artifact pruning. | Runtime behavior, screenshot freshness, or human desktop acceptance. | Re-run dashboard only when runtime artifacts need refreshing; it was skipped here to avoid unrelated `artifacts/quality/*` churn. |
| `git diff --check` / `git diff --cached --check` / current-doc stale-path scan | PASS / PASS / no current-doc matches for pruned wizard variants or legacy replay paths. | The cleanup diff is whitespace clean and current docs no longer point readers to removed artifact variants. | Historical records may still mention old paths intentionally. | Keep historical references in records/worklog as provenance, not current artifact entrances. |

## 2026-05-14 Artifact Duplicate-Screenshot Cleanup Checkpoint

This artifact hygiene slice removed exact duplicate current-tree screenshots and updated the
capture scripts so the same duplicate PNGs should not be regenerated. It did not change backend
runtime behavior, Data Import UX layout, or the meaning of the retained evidence.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `find artifacts -type f -print0 | xargs -0 sha256sum ...` before and after cleanup | Before cleanup, exact duplicates existed for human-like `02/03`, training-completion `trained/turn-3`, and visualization `ready/saliency-map`; after cleanup, no duplicate hashes remain. | Current artifact tree no longer stores the same PNG bytes under multiple current evidence paths. | Visual freshness, human desktop acceptance, or product correctness. | Re-run the duplicate-hash audit after future screenshot refreshes. |
| Updated `scripts/dev/capture_human_like_product_walkthrough.py`, `scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py`, and `scripts/dev/capture_visualization_render_walkthrough.py` | Source-selection now reuses the dataset-page screenshot path, training-completion reuses the start-training turn screenshot for the trained checkpoint, and visualization readiness reuses the saliency render screenshot. | The duplicate cleanup is generator-backed instead of only deleting current files. | That the full walkthroughs still pass when regenerated on every platform. | Re-run full walkthrough capture only when refreshing UI evidence; this slice avoided rerunning Data Import UX artifacts while UX work is still in progress. |
| `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py tests/unit/scripts/test_capture_visualization_render_walkthrough.py -q` | `14 passed`. | The script payload render/validation contracts for the touched local-training and visualization artifacts remain green. | Full local-model walkthrough runtime, human desktop acceptance, or human-like walkthrough regeneration. | Pair with full capture scripts before claiming refreshed runtime evidence. |
| Focused `ruff check` / `ruff format --check` / `basedpyright` on touched capture scripts and focused unit tests | PASS / PASS / `0 errors, 0 warnings, 0 notes`. | The changed artifact generator code is lint, format, and type clean. | Runtime behavior by itself. | Keep generator changes covered by focused tests and artifact audits. |
| `poetry run mkdocs build --strict` / `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `git diff --check` | PASS / `Architecture compliant!` / `97 passed` / PASS. | Docs and architecture guards remain green after artifact index and generator cleanup. | Product runtime, screenshot freshness, or release acceptance. | Keep artifact cleanups paired with strict docs and stale-reference scans. |

## 2026-05-14 Product UI No-Crash Evidence Guard Checkpoint

This test-quality slice rewrote one weak product-success integration test that only proved
`VisualizationPanel` could be constructed. The replacement now verifies the no-ready-state
product behavior through `VisualizeCommand` failure truth, exact blocked reason, exception
diagnostics, cleared plan/run controls, and the UI-visible saliency error label. The architecture
guard now also treats `initialization` / `initializes` names and generic
`assert isinstance(panel, SomePanel)` checks as weak evidence inside product-success integration
directories.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/integration/pipeline/test_e2e_training.py::TestVisualizationPanelIntegration::test_visualization_panel_without_ready_state_uses_command_blocked_reason -q` | `1 passed`. | The formerly no-crash visualization panel test now checks command-backed blocked behavior and visible UI state. | Full visualization runtime, saliency render freshness, or human desktop acceptance. | Keep replacing generic initialization tests with command/result/UI-visible assertions. |
| `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/integration/pipeline/test_e2e_training.py -q` | `9 passed`. | The affected training/evaluation/visualization integration file remains green after strengthening the visualization evidence. | Full pipeline smoke or real-data IO coverage. | Pair with tiny pipeline smoke when production behavior changes, not for this test-only cleanup. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `100 passed` / `Architecture compliant!`. | Architecture guard now blocks product-success integration tests named like generic initialization evidence or relying on generic panel instance assertions. | Every possible weak assertion shape. | Add more exact-evidence guards only after finding a real weak pattern in current product-success tests. |
| Focused `ruff check` / `ruff format --check` / `basedpyright` on touched Python files / `git diff --check` | PASS / PASS / `0 errors, 0 warnings, 0 notes` / PASS. | The test and guard changes are lint, format, type, and whitespace clean. | Runtime behavior by itself. | No docs-site claim until `mkdocs build --strict` is rerun after this validation entry. |

## 2026-05-14 Product Status Readability Checkpoint

This docs-only slice refreshed the first-screen status in `docs/index.md`,
`docs/architecture/README.md`, and `docs/planning/now.md`. It clarifies that
`BackendFacade` removal, artifact pruning, dashboard PASS, and product-success weak-evidence
guards are real progress but do not imply full zero-controller UI or human Windows acceptance.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run mkdocs build --strict` | PASS. | Documentation still builds strictly after readability edits. | Source correctness or runtime behavior. | Keep current truth in `docs/current.md` once the existing Data Import dirty docs are ready to stage. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `100 passed`. | Docs did not trip current-truth overclaim guards, and the architecture guard suite remains green. | Human desktop acceptance or full zero-controller UI. | Continue keeping target-state language out of current architecture summaries. |
| `git diff --check` | PASS. | Docs diff is whitespace clean. | Content completeness by itself. | Pair future docs readability edits with a quick stale-link / claim-boundary scan. |

## 2026-05-14 AgentManager Montage Query Evidence Checkpoint

This assistant UI test slice protects the montage dialog channel-name path. Real `Study` contexts
must use `QueryStateCommand(query="state")`; query success must not fall back to
`study.epoch_data`, and query failure must surface a blocked message instead of reading legacy
state.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/components/test_agent_manager.py::TestAgentManagerMethods::test_montage_channel_names_use_query_state_before_legacy tests/unit/ui/components/test_agent_manager.py::TestAgentManagerMethods::test_montage_channel_query_failure_blocks_without_legacy_fallback -q` | `2 passed`. | AgentManager montage channel lookup uses command/query truth before legacy fallback, and query failure is UI-visible. | Full montage picker UX or human desktop acceptance. | Add a human click-through artifact before claiming assistant-driven montage setup is release-ready. |
| `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/components/test_agent_manager.py -q` | `34 passed`. | Existing AgentManager UI behavior remains green after adding montage query evidence. | Local LLM long-session runtime. | Pair with local runtime smoke when touching model execution. |
| Focused `ruff check` / `ruff format --check` / `basedpyright` on `tests/unit/ui/components/test_agent_manager.py` | PASS / PASS / `0 errors, 0 warnings, 0 notes`. | The test addition is lint, format, and type clean. | Runtime behavior by itself. | Keep assistant UI tests focused on visible state and command/query truth. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `git diff --check` | `Architecture compliant!` / `100 passed` / PASS. | Architecture and whitespace guards remain green. | Human acceptance or full zero-controller UI. | Continue classifying legacy assistant paths as mock/legacy only unless a real product path still needs cleanup. |

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

## Human Windows Desktop Acceptance Gap

Automated gates are green enough for engineering health, but they still do not close desktop
acceptance. Before release or product-complete claims, a human Windows run must record the real
screen, branch/commit, launch method, selected data, expected result, observed result, and any
blocked step.

| Manual path | Must prove | Current blocker / missing artifact |
| --- | --- | --- |
| Launcher -> MainWindow visible | Launcher starts the intended repo/app, MainWindow appears on the active monitor, and geometry is usable. | Startup smoke exists; human Windows click-through notes and screenshots are still missing. |
| Data Import folder/file -> Preview -> Review and Import -> Apply | Selected EEG files and selected label carriers are visibly distinct from scan location and exactly the selected scope is applied. | Automated wizard screenshots exist; human selected-scope acceptance is still missing. |
| Preprocess -> Epoch A01T/A02T/A03T style data | Epoch command returns, UI remains responsive, no blocking success modal hides the app, and displayed state matches command result. | Offscreen real-GDF smoke exists; human Windows rerun after UX changes is still missing. |
| Dataset split -> training readiness | Split action generates non-empty train/validation/test summary and unlocks training readiness through command state. | Backend/ApplicationService evidence exists; human desktop observation of the visible training gate is still missing. |
| Training confirmation -> running / stopped status | Start Training requires confirmation, starts the command-backed run, and UI status/progress does not rely on stale controller echo. | Product smokes exist; long human run and interruption/recovery notes are still missing. |
| Assistant local runtime unavailable / available | Missing local LLM is visible and non-crashing; available local model can complete a normal command-state interaction. | Local runtime smokes exist; long desktop assistant session and unavailable-state click-through are still missing. |

Minimum acceptance record:

- branch and commit;
- Windows version, launch command/shortcut, Qt platform details when available;
- dataset path/category without leaking private data;
- screenshots or artifact paths for each major step;
- expected result versus observed result;
- explicit blocker if any step cannot be completed.

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
- `artifacts/ui/data-import-wizard-steps/03-review-metadata-smart-parse.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-internal-eeg-labels.png`
- `artifacts/ui/data-import-wizard-steps/match-label-placement-modes/eeg-event-order-full.png`
- `artifacts/ui/data-import-wizard-steps/match-label-placement-modes/label-time-full.png`
- `artifacts/ui/data-import-wizard-steps/match-label-placement-modes/label-interval-full.png`
- `artifacts/ui/data-import-wizard-steps/match-label-placement-modes/label-event-code-full.png`
- `artifacts/ui/data-import-wizard-steps/05-review-and-import-normal.png`

## 2026-05-13 Real-Data IO Shape-Evidence Checkpoint

This test-hygiene slice did not change runtime behavior or Data Import UX. It strengthened
`tests/integration/io/test_io_integration.py` so fixture loading no longer passes only because
MNE returned a non-`None` object. Compact and public EEG fixture checks now assert loaded data
rank, non-empty sample content, and channel-axis agreement with `Raw.get_nchan()`; resolved GDF
duplicate-channel detail is also asserted as a dictionary before key checks.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` | `31 passed, 8 warnings` | Real-data IO fixture tests load data arrays with expected dimensionality and channel axis instead of generic no-crash / non-`None` evidence. | Scientific reproducibility, all possible external EEG files, or human Data Import acceptance. | Continue replacing generic assertions in nearby metadata / pipeline integration tests only when replacement evidence is stronger. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/integration/io/test_io_integration.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed test code is lint/type/format clean. | Runtime behavior by itself. | Keep focused gates paired with the behavior test. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed` | Strengthened IO evidence did not weaken architecture guard coverage. | Semantic proof outside guarded files. | Broaden guard scope only with concrete replacement behavior. |

## 2026-05-13 Metadata Real-Data Event-Evidence Checkpoint

This test-hygiene slice did not change runtime behavior or Data Import UX. It tightened
`tests/integration/io/test_metadata_integration.py` from a generic `raw is not None` plus random
label smoke into deterministic metadata evidence over the A01T GDF fixture: raw data shape,
fixed-position filename parsing, label-file round trip, event array shape, onset/previous-value
alignment, and final event IDs are now asserted explicitly.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/io/test_metadata_integration.py -q` | `1 passed` | The metadata pipeline test now proves deterministic label-to-event replacement against a real GDF fixture instead of random/no-crash behavior. | Data Import UX acceptance, all external label heuristics, or scientific validation. | Continue replacing weak pipeline assertions only when the replacement checks real state or UI-visible results. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/integration/io/test_metadata_integration.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed test code is lint/type/format clean. | Runtime behavior by itself. | Keep deterministic tests preferred over random fixture generation. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed` | Strengthened metadata evidence did not weaken architecture guard coverage. | Semantic proof outside guarded files. | Broaden guard scope only with concrete replacement behavior. |

## 2026-05-13 Preprocess Controller Shape/Event-Evidence Checkpoint

This test-hygiene slice kept the boundary explicit: `tests/integration/controller/test_preprocess_controller.py`
is lower-level controller evidence, not UI refresh or product command-spine acceptance. The suite now checks
that controller data is a `Raw` wrapper, signal arrays are non-empty with the expected channel axis, filtering
preserves shape while changing variance, epoch extraction creates a real `(n_events, 3)` matrix for the selected
event code, and reset returns to raw data with cleared preprocess history.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/controller/test_preprocess_controller.py -q` | `4 passed` | Lower-level preprocess controller behavior is protected by shape/event/history assertions instead of generic `None` checks. | Product command-spine success, UI refresh acceptance, or zero-controller UI architecture. | Keep product-facing preprocess evidence in ApplicationService / command tests. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/integration/controller/test_preprocess_controller.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed test code is lint/type/format clean. | Runtime behavior by itself. | Continue keeping controller tests classified as lower-level contracts. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed` | Strengthened controller evidence did not weaken architecture guard coverage. | Semantic proof outside guarded files. | Do not use this controller suite to justify product UI bypasses. |

## 2026-05-13 Preprocess Validation Deterministic-Evidence Checkpoint

This test-hygiene slice kept runtime and UI unchanged. `tests/integration/pipeline/test_preprocess_validation.py`
now builds its synthetic EEG fixture with a fixed random seed and asserts concrete state after resample,
filter -> epoch, history tracking, and reset. The suite no longer relies on `get_first_data()` only being
non-`None` or on nondeterministic signal generation.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_preprocess_validation.py -q` | `4 passed` | Synthetic preprocess validation now proves deterministic signal shape, event code preservation, epoch shape, operation history, and reset shape. | Real-data product acceptance, UI responsiveness, all preprocess edge cases, or scientific validation. | Keep real-GDF product preprocess evidence in command/UI smokes. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/integration/pipeline/test_preprocess_validation.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed test code is lint/type/format clean. | Runtime behavior by itself. | Prefer fixed synthetic fixtures over random data in regression tests. |

## 2026-05-13 AgentManager Montage Command-Evidence Checkpoint

This test-hygiene slice did not change runtime behavior or redesign montage UX. It tightened
`tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker` so real-Study montage evidence
no longer treats `Study.epoch_data.set_channels(...)` as product success. The suite now checks
that the dialog's channel list is read through `QueryStateCommand(query="state")`, then verifies
the exact `ApplyMontageCommand` payload for channels, normalized 3D positions, and montage name.
Mock / legacy fallback coverage remains separate compatibility evidence.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker -q` | `9 passed` | AgentManager montage tests now assert command-visible channel source and apply payload instead of `Study.epoch_data` side effects. | Human montage-dialog acceptance, full zero-controller UI, or final Data Import UX. | Continue retiring UI controller/read-only exceptions one behavior at a time. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/unit/ui/test_agent_manager_coverage.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed test code is lint/type/format clean. | Runtime behavior by itself. | Keep command-shape assertions paired with compatibility fallback tests. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed` | The command-evidence rewrite did not weaken current architecture guards. | Semantic proof for every UI controller path. | Add guard examples only after concrete replacement behavior exists. |

## 2026-05-13 A01T Real-Data Pipeline Exact-Evidence Checkpoint

This test-evidence slice did not change product runtime or UX. It tightened
`tests/integration/pipeline/test_real_data_pipeline.py` so the A01T command-spine smoke no longer
passes on generic non-empty event, split, or history checks. The smoke now verifies the exact
deduplicated event-name set, ApplicationService epoch-state event IDs and shape, deterministic
trial split counts, and one-run training-history state.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red alignment run after replacing non-empty split evidence with exact summary | Failed because the expected summary initially omitted the command-state `audit` payload. | The strengthened assertion reads the full dataset split summary shape instead of only checking counts. | Runtime correctness by itself. | Keep exact evidence tied to known checked-in fixtures. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_real_data_pipeline.py -q` | `1 passed` | A01T load -> preprocess -> epoch -> split -> configure -> train succeeds through ApplicationService commands with exact event IDs, epoch shape, split summary, and one training-history row. | Training quality, all real datasets, or human Windows desktop acceptance. | Keep cross-source/public fixture coverage separate from this A01T smoke. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/integration/pipeline/test_real_data_pipeline.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed test code is lint/type/format clean. | Runtime behavior by itself. | Prefer fixed fixture expectations over generic non-empty checks. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed` | The exact-evidence rewrite did not weaken current architecture guards. | Semantic proof for every pipeline test. | Expand guard scope only with replacement command/query evidence. |

## 2026-05-13 Checked-In GDF/MAT Exact-Evidence Checkpoint

This test-evidence slice kept runtime and UX unchanged. It tightened
`tests/integration/pipeline/test_checked_in_real_dataset_validation.py` so the A01T/A02T/A03T
label-attached real-data smokes no longer pass only because datasets and training history are
non-empty. The suite now verifies exact label event IDs, `(288, 3)` attached-label event shape,
per-fixture epoch counts, epoch shape, deterministic trial split summaries, and one-row
training-history results.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_checked_in_real_dataset_validation.py -q` | `6 passed` | A01T/A02T/A03T GDF+MAT smokes prove exact label event shape, epoch counts, split summaries, and one-run training history through ApplicationService commands. | Training quality, all subjects, all EEG formats, or human Windows acceptance. | Keep this as fixture-specific evidence; use public cross-source smoke for format breadth. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/integration/pipeline/test_checked_in_real_dataset_validation.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed test code is lint/type/format clean. | Runtime behavior by itself. | Continue converting weak real-data assertions only where fixture expectations are stable. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed` | The exact-evidence rewrite did not weaken current architecture guards. | Semantic proof for every real-data fixture path. | Add guard coverage only when replacement evidence exists. |

## 2026-05-13 Public Cross-Source Command-Evidence Checkpoint

This test-evidence slice kept runtime and UX unchanged. It tightened
`tests/integration/pipeline/test_public_cross_source_training_smoke.py` without pretending public
fixtures are one exact subject: each fixture still owns its expected event names. The suite now
checks command-owned epoch event mapping, requires split totals to match epoch count, preserves
split-audit payload checks, and verifies one completed training run/history row.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_public_cross_source_training_smoke.py -q` | `4 passed, 3 warnings` | EDF/GDF/SET/CNT public fixtures exercise ApplicationService load -> preprocess -> epoch -> split -> configure -> train with event mapping and split-total evidence. | Training quality, full format certification, or human Windows acceptance. | Keep warnings classified as parser/runtime metadata warnings unless they hide product failure. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/integration/pipeline/test_public_cross_source_training_smoke.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed test code is lint/type/format clean. | Runtime behavior by itself. | Keep format-breadth assertions tied to fixture-owned event IDs. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed` | The command-evidence rewrite did not weaken current architecture guards. | Semantic proof for every external EEG file. | Add exact expectations only where fixture outputs are stable. |

## 2026-05-13 ApplicationService Exact-Split Evidence Checkpoint

This backend test-evidence slice kept runtime behavior unchanged. It tightened
`tests/integration/backend/test_application_service_workflow.py` so the core synthetic
ApplicationService workflow and dialog-generator split path no longer pass on generic non-empty
dataset counts. They now verify the full command-state split summary, including train/val/test
counts and the split-audit payload.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` | `8 passed` | Core ApplicationService load -> preprocess -> epoch -> dataset workflow and dialog-generator split evidence use exact split summaries instead of non-empty counts. | UI refresh acceptance, real-data breadth, or human Windows acceptance. | Keep this as synthetic command-spine evidence paired with real-data smokes. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/integration/backend/test_application_service_workflow.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed test code is lint/type/format clean. | Runtime behavior by itself. | Preserve exact split-audit assertions when refactoring dataset generation. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed` | The exact-split rewrite did not weaken current architecture guards. | Semantic proof for every backend workflow. | Expand product-success guards only with replacement command/query evidence. |

## 2026-05-13 Real-Tool Chain Exact-Evidence Checkpoint

This test-evidence slice kept real tool behavior unchanged. It tightened
`tests/integration/pipeline/test_integration_real_tools.py` so the A01T LLM real-tool chain no
longer treats dataset `count > 0` or `plan_count >= 1` as enough. The chain now checks exact
ApplicationService state after tool-driven epoching, exact generated dataset split summary, exact
dataset tool result text, and one completed training run.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_integration_real_tools.py -q` | `4 passed` | LLM real tools still route through ApplicationService and now expose exact A01T epoch, dataset, and training state evidence. | Tool-call benchmark accuracy, human assistant UX, or long local-model runtime. | Keep tool-call eval separate from real-tool backend state smokes. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/integration/pipeline/test_integration_real_tools.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed test code is lint/type/format clean. | Runtime behavior by itself. | Keep exact state assertions aligned with command result schema. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed` | The real-tool test rewrite did not weaken current architecture guards. | Semantic proof for every assistant path. | Broaden real-tool exact evidence only after stable fixture expectations exist. |

## 2026-05-13 UI Product Walkthrough Exact-State Evidence Checkpoint

This UI test-evidence slice did not redesign UI or Data Import. It tightened
`tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions`
so the user-facing offscreen walkthrough checks exact command-visible epoch and dataset split state
after clicking through import, preprocess, epoch, split, configure, and dry-run train.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions -q` | `1 passed` | The touched product walkthrough now asserts exact epoch count/channel/time/event state and exact dataset split summary after user-facing actions. | Human Windows desktop acceptance or final UX approval. | Keep human click-through separate from offscreen UI smoke. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/ui/test_product_walkthrough.py -q` | `4 passed` | The broader product walkthrough file remains green after exact-state assertions. | Complete desktop acceptance or full zero-controller UI. | Pair with human artifact when release claims are needed. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `tests/integration/ui/test_product_walkthrough.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | Changed UI test code is lint/type/format clean. | Runtime behavior by itself. | Keep exact UI smoke state aligned with ApplicationService query schema. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `91 passed` | The UI product walkthrough rewrite did not weaken current architecture guards. | Human product acceptance. | Continue replacing weak UI assertions only with stronger UI-visible or command-state evidence. |

## 2026-05-14 Fast Dashboard After Exact-Evidence Stack

After the exact-evidence stack for ApplicationService workflow, real-data pipeline, checked-in
GDF/MAT fixtures, public cross-source fixtures, real tools, and the UI product walkthrough, the
fast quality dashboard was rerun from the current branch state. This refreshes engineering-health
evidence only; it still does not close human Windows acceptance or full product completion.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-14 00:11:43 UTC+08:00`; UI unit suite `1137 passed`; real-data IO `31 passed, 8 warnings`. | Branch health remains green after the exact-evidence stack, including full ruff, basedpyright, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete, human Windows desktop acceptance, long local-model session, or scientific validation. | Keep human desktop acceptance and local-model session evidence separate. |

## 2026-05-13 Test Evidence Cleanup Fast Dashboard

After the real-data IO shape, metadata event, and lower-level preprocess controller evidence
cleanup slices, the fast dashboard was rerun on the stacked branch state. This refreshes the
engineering-health signal for the current branch, but it still does not close human Windows
desktop acceptance or product-complete claims.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 23:20:52 UTC+08:00`; UI unit suite `1137 passed`; real-data IO `31 passed, 8 warnings`. | Fast engineering dashboard remains green after the test-evidence cleanup stack, including full ruff, basedpyright, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete, human Windows acceptance, long local-model session, or scientific validation. | Treat dashboard as health evidence only; keep human desktop acceptance separate. |

## 2026-05-13 Docs Readability and UI Refresh Truth Checkpoint

This slice kept UX work separate: no Data Import UX redesign, no Match Labels / Review and
Import redesign, and no answer UI redesign. The change was docs-first: `current.md`,
`architecture/ui.md`, and this validation page now start with concise current-truth summaries,
remaining-exception maps, and evidence-reading guidance instead of forcing readers to infer the
state from chronological checkpoint history.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Source audit: `rg` over `XBrainLab/ui`, `XBrainLab/llm`, `XBrainLab/mcp`, guarded integration tests, and architecture guards for `run_legacy_controller_fallback`, `get_legacy_controller_from_study`, `study.get_controller`, direct mutable `Study` state, and `BackendFacade` | Remaining hits classified as panel bootstrap / observer bridge, mock / legacy compatibility, human-in-loop UI request, or lower-level setup/evidence boundary. | Docs now expose the actual remaining controller exception classes instead of presenting a vague clean/dirty claim. | Full zero-controller UI or proof that every lower-level integration test is product evidence. | Continue retiring one exception class at a time; do not broaden guards before replacement coverage exists. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Docs site still builds strictly and docs diff has clean whitespace after readability rewrite. | Content correctness by itself. | Keep readability edits tied to source/test audits. |
| `poetry run python tests/architecture_compliance.py` / `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `Architecture compliant!` / `79 passed` | Existing architecture guards still reject known UI/backend legacy regressions after the docs rewrite. | Runtime acceptance for paths outside guard scope. | Add new guard examples only with concrete replacement behavior. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/ui/test_ui_refresh.py tests/integration/ui/test_ui_integration.py tests/integration/ui/test_panel_controller_binding.py -q` | `8 passed` | UI launch/navigation/tab-refresh and injected controller event wiring evidence still matches the documented UI refresh truth. | Human Windows desktop acceptance or full zero-controller UI. | Keep UI refresh smokes paired with command/query truth assertions. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/ui/test_product_walkthrough.py -q` | `4 passed` | Representative product walkthrough remains green while docs describe product-smoke claim boundaries. | Long-running local model session, release approval, or all data formats. | Human desktop acceptance remains required before release claims. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 17:46:11 UTC+08:00`. | Fast engineering dashboard is green after docs readability cleanup, including full ruff, basedpyright, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete or human Windows acceptance. | Keep docs readability scored separately from docs correctness/completeness. |

## 2026-05-13 Docs Navigation Readability Checkpoint

This docs-only slice aligned `index.md`, `planning/now.md`, and `architecture/README.md` with the
newer current/UI/validation truth. The goal was to make the site entry and short-term plan readable
without implying that `BackendFacade` removal means full zero-controller UI or human product
acceptance.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Docs entry audit: compared `docs/index.md`, `docs/planning/now.md`, `docs/architecture/README.md`, `docs/current.md`, and this validation page for current-vs-target wording | Entry docs now describe remaining gaps as UI controller adapter distance, product-smoke evidence boundaries, and human desktop acceptance rather than stale facade cleanup. | New readers can reach the current state and next work without reading chronological history first. | Runtime behavior or product acceptance. | Keep `now.md` current after each major stabilization checkpoint. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Documentation site and whitespace gate remain clean after entry-navigation edits. | Content correctness by itself. | Pair docs edits with source/test audits when implementation claims change. |
| `poetry run python tests/architecture_compliance.py` | `Architecture compliant!` | The source tree still passes the architecture guard while docs classify `BackendFacade` as a guarded regression risk, not current implementation. | Human desktop acceptance or full zero-controller UI. | Keep architecture docs and guard vocabulary aligned. |

## 2026-05-13 ApplicationService Workflow Query-Evidence Checkpoint

This test/guard slice tightened backend product-evidence boundaries without touching UX. The
non-mocked `test_application_service_workflow.py` no longer creates a dialog-like dataset generator
through `service.study.get_datasets_generator(...)`; it now queries
`QueryStateCommand(query="dataset_generation_context", include_objects=True)` and builds the dialog
generator from the command-owned epoch object before dispatching `GenerateDatasetCommand`.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_application_service_accepts_dialog_generator_split_and_updates_readiness -q` | `1 passed` | The dialog-generator split workflow can be proven through ApplicationService query diagnostics plus `GenerateDatasetCommand`, not direct `Study` generator calls. | Every pipeline/domain integration test is product evidence. | Continue migrating one suite at a time before broadening guards. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` | `8 passed` | The full non-mocked ApplicationService workflow suite remains green after query-truth replacement. | Human desktop acceptance or full UI zero-controller architecture. | Keep this suite in command-spine validation. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `80 passed` / `Architecture compliant!` | Architecture guard now includes `tests/integration/backend/test_application_service_workflow.py` in direct `Study` product-evidence checks. | Semantic proof outside guarded files. | Expand guard scope only after replacement command/query evidence exists. |
| Focused `ruff` / `basedpyright` on changed Python files | PASS / `0 errors, 0 warnings, 0 notes` | Changed Python files are lint/type clean. | Runtime behavior by itself. | Dashboard also ran below. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 19:45:45 UTC+08:00`. | Fast engineering dashboard is green after this guard/test slice, including full ruff, basedpyright, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete or human Windows acceptance. | Keep dashboard as health evidence, not product acceptance. |

## 2026-05-13 Training Command/Query State-Evidence Checkpoint

This test-hygiene slice kept UX and training runtime behavior unchanged. The old training
integration evidence that implied UI-facing code should read `Study.training_option` directly
was replaced with `ConfigureTrainingCommand` plus `QueryStateCommand(query="state")`. The lower-level
`Study.training_option` compatibility contract remains covered in a unit/domain test instead of
being treated as product-success evidence.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red guard check after adding `tests/integration/training/test_training_integration.py` to the direct-state product-success guard | Failed on the expected `study.training_option` reads before the test rewrite. | The new guard scope would have caught the stale training integration evidence. | Runtime behavior by itself. | Keep direct `Study` contracts in unit/domain tests only. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/training/test_training_integration.py::TestApplicationServiceTrainingStateIntegration::test_training_option_is_exposed_through_command_state -q` | `1 passed` | UI-facing training configuration truth is observable through ApplicationService command state and query diagnostics. | Actual training quality, long-running training, or desktop acceptance. | Keep training UI actions paired with command result/state assertions. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/training/test_training_integration.py -q` | `22 passed` | Existing training integration bug-fix coverage remains green after removing product direct-state evidence. | Full product workflow or all training edge cases. | Continue classifying lower-level pipeline training tests before broadening guards. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/backend/test_study_training_contract.py -q` | `2 passed` | `Study.training_option` remains explicitly covered as a lower-level compatibility contract. | Product command-spine evidence. | Do not use this unit contract as UI/backend product success. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `81 passed` / `Architecture compliant!` | Architecture guard now rejects `study.training_option` success evidence in the training integration suite. | Semantic proof outside guarded files. | Expand guard scope only after replacement command/query evidence exists. |
| Focused `ruff` / `basedpyright`, `poetry run mkdocs build --strict`, `git diff --check` | PASS / `0 errors, 0 warnings, 0 notes` / PASS / PASS | Changed Python files are lint/type clean, docs build strictly, and whitespace is clean. | Runtime behavior by itself. | Continue running focused gates before each checkpoint commit. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 19:58:33 UTC+08:00`. | Fast engineering dashboard remains green after this training test/guard slice, including full ruff, basedpyright, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete, human Windows acceptance, or training quality. | Keep dashboard as engineering health evidence only. |

## 2026-05-13 LLM Pipeline Stage Command-Truth Checkpoint

This runtime slice removed a real-product fallback in assistant stage calculation. For real
`Study` objects, `compute_pipeline_stage()` now uses ApplicationService state snapshots only and
fails closed to `EMPTY` if the snapshot cannot be read. The direct `Study` state fallback remains
available only for mock / legacy Study-shaped objects used by unit compatibility tests.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red test: `poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py::TestComputePipelineStage::test_real_study_does_not_fallback_to_direct_state_when_service_fails -q` before the fix | Failed as expected: real `Study` with a failing service snapshot reported `DATA_LOADED` from direct `loaded_data_list`. | The test reproduced the ApplicationService-bypass fallback risk. | Full agent runtime acceptance. | Keep product session stage truth command-owned. |
| Same focused test after the fix | `1 passed` | Real `Study` stage now fails closed instead of falling back to mutable state when ApplicationService snapshot fails. | Correctness of every possible tool prompt. | Add product-level assistant walkthrough before release claims. |
| `poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py -q` | `25 passed` | Pipeline stage compatibility behavior remains covered, including mock fallback and real ApplicationService snapshot path. | Tool-call benchmark accuracy. | Keep mock fallback explicitly labeled compatibility. |
| `poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/agent/test_context_assembler.py -q` | `41 passed` | Agent context assembly remains compatible with command-owned stage truth. | Long-running local model session or external MCP client certification. | Pair with runtime assistant smoke later. |
| Focused `ruff` / `basedpyright` on changed Python files, plus `poetry run python tests/architecture_compliance.py` | PASS / `0 errors, 0 warnings, 0 notes` / `Architecture compliant!` | Changed code is lint/type clean and does not violate current architecture guard. | Product complete. | Run docs/dashboard gates before committing this checkpoint. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_llm_direct_study_state_guard_flags_product_stage_read tests/unit/test_architecture_compliance.py::test_llm_direct_study_state_guard_allows_legacy_stage_helper -q` | `2 passed` | Architecture guard now has examples that reject LLM product direct `Study` state reads while preserving the named legacy helper boundary. | Semantic proof for every LLM function. | Keep direct Study fallback isolated to explicit legacy helpers. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `83 passed` / `Architecture compliant!` | Full architecture guard suite includes the LLM direct-state product boundary. | Runtime acceptance by itself. | Continue adding guard examples only with replacement behavior. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Documentation builds strictly and whitespace remains clean after current-truth updates. | Content is automatically complete. | Keep docs edits tied to source/test evidence. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 20:22:13 UTC+08:00`. | Fast engineering dashboard remains green after this LLM stage command-truth slice, including full ruff, basedpyright, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete, human Windows acceptance, long local-model session, or tool-call accuracy. | Keep dashboard as engineering health evidence only. |

## 2026-05-13 Docs Current-Truth Overclaim Guard Checkpoint

This guard slice protects documentation readability and claim boundaries. It scans the current-truth
entry docs (`current.md`, `index.md`, `architecture/README.md`, `architecture/ui.md`,
`architecture/backend.md`, `planning/now.md`, and this validation page) for unbounded claims that
present product completion, full zero-controller UI, human Windows desktop acceptance, or release
approval as current fact. Lines inside explicit boundary contexts such as "cannot claim",
"cannot replace", "not supported", "gap", or "missing" remain allowed.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red test: docs overclaim checker import before implementation | Failed as expected because `check_docs_current_truth_overclaims` did not exist. | The new guard was introduced test-first. | Runtime behavior. | Keep docs guards narrow enough to avoid blocking boundary language. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_docs_current_truth_guard_flags_product_complete_overclaim tests/unit/test_architecture_compliance.py::test_docs_current_truth_guard_allows_explicit_claim_boundaries -q` | `2 passed` | Guard rejects positive overclaim examples and allows explicit current-truth boundary language. | Human acceptance itself. | Add phrases only when current docs create real risk. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `85 passed` / `Architecture compliant!` | Full architecture guard suite now includes docs current-truth overclaim protection. | Content quality beyond the guarded phrases. | Keep human-written docs review as the main readability check. |
| Focused `ruff` / `basedpyright` on changed guard files | PASS / `0 errors, 0 warnings, 0 notes` | Changed checker and tests are lint/type clean. | Runtime behavior. | Run docs build before commit. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Docs still build strictly and whitespace is clean after guard-evidence updates. | Content is automatically complete. | Keep docs review separate from build success. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 20:39:30 UTC+08:00`. | Fast dashboard remains green with the docs overclaim guard in the default architecture-compliance gate. | Product complete or human acceptance. | Dashboard remains engineering health evidence only. |

## 2026-05-13 Real-Data Pipeline Command-Spine Checkpoint

This test-evidence slice kept UX untouched and moved `test_real_data_pipeline.py` from direct
`Study` orchestration to the product command spine. The real GDF smoke now runs
`LoadDataCommand -> PreprocessCommand -> CreateEpochCommand -> GenerateDatasetCommand ->
ConfigureTrainingCommand -> TrainCommand`, then reads state, split audit, and training history
through command results / `QueryStateCommand`. The only object access is a command-owned
`QueryStateCommand(include_objects=True)` fixture hook used to deduplicate the checked-in GDF
events before epoching.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red guard check after adding `tests/integration/pipeline/test_real_data_pipeline.py` to the direct-state product-success guard | Failed on the expected `study.preprocessed_data_list`, `study.epoch_data`, `study.trainer`, and `study.get_datasets_generator()` reads before the rewrite. | The new guard scope would have caught this suite if it kept using mutable `Study` state as product evidence. | Runtime behavior by itself. | Keep lower-level direct `Study` tests out of product-success guard until replacement command evidence exists. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_real_data_pipeline.py -q` | `1 passed` | The real A01T GDF load -> preprocess -> epoch -> dataset -> one-epoch train smoke succeeds through ApplicationService commands and command-visible state/history. | Training quality, all real datasets, or human Windows desktop acceptance. | Keep this as command-spine smoke, not scientific validation. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `86 passed` / `Architecture compliant!` | Architecture guard now includes the real-data pipeline smoke in direct `Study` product-evidence checks. | Semantic proof outside guarded files. | Expand guard scope only one suite at a time after replacement behavior is in place. |
| Focused `ruff` / `basedpyright` on changed Python files | PASS / `0 errors, 0 warnings, 0 notes` | Changed test and guard code are lint/type clean. | Runtime behavior by itself. | Run docs build and dashboard before checkpoint commit. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Documentation builds strictly and whitespace remains clean after current-truth and validation updates. | Content is automatically complete. | Keep docs review separate from build success. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 20:54:34 UTC+08:00`. | Fast engineering dashboard remains green after this command-spine test/guard slice, including full ruff, basedpyright, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete, training quality, or human Windows acceptance. | Dashboard remains engineering health evidence only. |

## 2026-05-13 Training UI Command-State Evidence Checkpoint

This test-evidence slice kept visible Training UI behavior unchanged while narrowing the claim
boundary of `tests/integration/pipeline/test_e2e_training.py`. The file is now described as
training UI / Study compatibility regression coverage with mocked trainers, not as complete
product workflow evidence. Its UI-facing string-epoch coercion check now configures training
through `ConfigureTrainingCommand` and verifies normalized state through `QueryStateCommand`
instead of reading `study.training_option` directly.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red guard check after adding `tests/integration/pipeline/test_e2e_training.py` to the direct-state product-success guard | Failed on the expected `study.training_option` reads before the rewrite. | The guard would catch this E2E-named suite if it used mutable `Study` state as product evidence. | Runtime behavior by itself. | Keep mock trainer setup classified as UI panel regression, not product workflow proof. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_e2e_training.py::TestTrainingWorkflowWithUI::test_progress_bar_calculation_with_string_epoch -q` | `1 passed` | String epoch / batch / learning-rate UI-style inputs normalize through ApplicationService command state before the panel renders progress. | Full training workflow or training quality. | Keep product training smokes in command/query suites. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_e2e_training.py::TestTrainingPanelRealUsage::test_update_loop_type_safety -q` | `1 passed` | Training history table regression now asserts exact row count, group/run/model/status/epoch cells, and rendered metric cells instead of generic non-empty progress text. | Product training quality or non-mocked training workflow. | Keep this classified as UI panel compatibility evidence. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_e2e_training.py::TestEvaluationPanelIntegration::test_evaluation_panel_with_unfinished_trainer_shows_unavailable_state -q` | `1 passed` | EvaluationPanel regression now asserts service-backed `available=False`, plan count, finished-run count, and `No Data Available` display for unfinished trainer data instead of generic combo population. | Finished evaluation UX or training quality. | Keep finished-run display proof in product walkthrough / evaluation panel tests. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_e2e_training.py::TestEvaluationPanelIntegration::test_evaluation_panel_with_no_trainer tests/integration/pipeline/test_e2e_training.py::TestTrainingWorkflowWithUI::test_progress_bar_calculation_with_string_epoch tests/integration/pipeline/test_e2e_training.py::TestTrainingWorkflowWithUI::test_update_loop_handles_string_metrics -q` | `3 passed` | No-trainer evaluation now asserts precondition failure and `No Data Available`; progress and string-metric regressions assert exact status/epoch/metric values instead of generic non-empty output. | Product training quality or human desktop acceptance. | Keep these as compatibility/UI regression checks. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_e2e_training.py -q` | `9 passed` | Existing Training / Evaluation / Visualization panel regression coverage remains green after replacing direct training-option success truth, strengthening progress-table assertions, and removing generic evaluation-combo evidence. | Human desktop acceptance or complete zero-controller UI. | Continue splitting mock-heavy UI panel tests from product-smoke evidence. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `87 passed` / `Architecture compliant!` | Architecture guard now includes the E2E-named training UI regression file in direct `Study` product-evidence checks. | Semantic proof outside guarded files. | Expand guard scope only after a concrete replacement assertion exists. |
| Focused `ruff` / `basedpyright` on changed Python files | PASS / `0 errors, 0 warnings, 0 notes` | Changed test and guard code are lint/type clean. | Runtime behavior by itself. | Run docs build and dashboard before checkpoint commit. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Documentation builds strictly and whitespace remains clean after current-truth and validation updates. | Content is automatically complete. | Keep docs review separate from build success. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 21:07:58 UTC+08:00`. | Fast engineering dashboard remains green after this training UI test/guard slice, including full ruff, basedpyright, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete, training quality, or human Windows acceptance. | Dashboard remains engineering health evidence only. |

## 2026-05-13 Preprocess Validation Command-Load Checkpoint

This small test-evidence slice kept the preprocess edge-case assertions controller-level, but moved
the synthetic FIF fixture load/setup success evidence onto the command spine. The fixture now loads
through `LoadDataCommand` and confirms raw state through `QueryStateCommand` before returning the
study to `PreprocessController` tests. The touched file also now asserts `get_first_data()` is
non-null through a tiny helper, keeping focused type checks clean.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red guard check after adding `tests/integration/pipeline/test_preprocess_validation.py` to the direct-state product-success guard | Failed on the expected `study.loaded_data_list` setup assertion before the rewrite. | The guard would catch this preprocess validation suite if it used mutable `Study` state as fixture-load success evidence. | Product preprocess workflow acceptance. | Keep direct controller assertions classified as controller-level regression unless converted to command tests. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_preprocess_validation.py::TestPreprocessValidation::test_filter_then_epoch_pipeline -q` | `1 passed` | Synthetic event regression now asserts exact `left` / `right` event names before epoching instead of generic non-empty event evidence. | Full product preprocess UI or all event formats. | Keep this classified as controller-level preprocessing regression. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_preprocess_validation.py -q` | `4 passed` | Synthetic FIF load setup is command-backed, and existing resample/filter/epoch/history/reset controller regressions remain green with exact event evidence. | Full product preprocess UI or all real data formats. | Use ApplicationService smokes for product workflow claims. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `88 passed` / `Architecture compliant!` | Architecture guard now includes the preprocess validation suite in direct `Study` product-evidence checks. | Semantic proof outside guarded files. | Expand guard scope only with replacement command/query assertions. |
| Focused `ruff` / `basedpyright` on changed Python files | PASS / `0 errors, 0 warnings, 0 notes` | Changed test and guard code are lint/type clean. | Runtime behavior by itself. | Run docs build and dashboard before checkpoint commit. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Documentation builds strictly and whitespace remains clean after current-truth and validation updates. | Content is automatically complete. | Keep docs review separate from build success. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 21:19:07 UTC+08:00`. | Fast engineering dashboard remains green after this preprocess validation fixture-load slice, including full ruff, basedpyright, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete, all preprocess UX paths, or human Windows acceptance. | Dashboard remains engineering health evidence only. |

## 2026-05-13 Preprocess Controller Test-Quality Checkpoint

This controller-level cleanup kept `PreprocessController` as the subject under test but stopped
using `DatasetController.import_files()` as the fixture-load path. The fixture now loads A01T
through `LoadDataCommand` and confirms raw state through `QueryStateCommand`. Generic
non-empty checks for events and history were narrowed to expected A01T event IDs and a concrete
Filtering history assertion.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/controller/test_preprocess_controller.py -q` | `4 passed` | Real GDF PreprocessController regressions still pass with command-backed fixture load and more specific event/history assertions. | Product UI preprocess acceptance or full command-only preprocess runtime. | Keep controller tests classified as lower-level regression evidence. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on `test_preprocess_controller.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS | The changed controller integration test is lint/type/format clean. | Runtime behavior by itself. | Pair with docs build and dashboard before checkpoint commit. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Documentation builds strictly and whitespace remains clean after current-truth and validation updates. | Content is automatically complete. | Keep docs review separate from build success. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 21:31:03 UTC+08:00`. | Fast engineering dashboard remains green after this controller integration test-quality slice, including full ruff, basedpyright, architecture, startup, UI baseline/dialog/unit, and real-data IO. | Product complete, UI preprocess acceptance, or human Windows acceptance. | Dashboard remains engineering health evidence only. |

## 2026-05-13 UI Current-Truth Readability Polish Checkpoint

This docs-only slice kept UX, backend runtime, and tests untouched. It tightened the reading path
for current UI architecture and the next-work plan so a new engineer can distinguish real product
runtime risks from quarantined controller adapter hits.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Source-doc audit of `docs/architecture/ui.md` and `docs/planning/now.md` | Confirmed the earlier duplicate `ApplicationService Readiness Gate` heading is no longer present; added reading guidance for UI controller hits and made the next engineering gap explicit. | Current docs are less likely to be read as either "everything is legacy" or "full zero-controller UI is done." | Runtime behavior, product acceptance, or proof that every UI display fallback is removed. | Keep retiring UI readonly display fallback one class at a time, with command/query evidence. |
| `poetry run mkdocs build --strict` / `poetry run python tests/architecture_compliance.py` / `git diff --check` | PASS / `Architecture compliant!` / PASS | Docs site still builds strictly, current-truth claim guards remain green, and the docs-only diff is whitespace clean. | Dashboard freshness, runtime behavior, or human Windows desktop acceptance. | Keep docs readability work tied to source/test evidence instead of chronological history alone. |

## 2026-05-13 Evaluation Display Command-Evidence Checkpoint

This UI-refresh slice fixed a stale display path in `EvaluationPanel`. When the service-backed
evaluation payload exists but does not contain average pooled metrics for the selected plan, the
panel now clears the metric views instead of leaving the previous run's metrics visible. The path
still refuses stale controller pooled-metric fallback for real `Study` contexts.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red test: `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py::test_evaluation_panel_clears_metrics_when_service_average_payload_missing -q` before the fix | Failed as expected with 3 stale metric rows left visible after selecting Average. | Reproduced a concrete UI refresh truth bug, not just a legacy-string finding. | Full evaluation UX acceptance. | Keep display-clearing behavior tied to command/query payload availability. |
| Same focused test after the fix | `1 passed` | Service-owned missing average metrics now clear stale displayed metrics without reading controller fallback. | Full product workflow. | Keep this as a focused regression. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py -q` | `12 passed` | EvaluationPanel query-first rendering and stale-fallback regression coverage remains green after the fix. | Human desktop acceptance or full zero-controller UI. | Pair with product walkthrough / human artifact before release claims. |
| Focused `ruff` / `basedpyright` / `ruff format --check` on changed Python files, plus architecture gates | PASS / `0 errors, 0 warnings, 0 notes` / PASS / `Architecture compliant!`, architecture unit `88 passed` | Changed EvaluationPanel code and tests are lint/type/format clean and do not violate current architecture rules. | Dashboard freshness or runtime coverage outside this panel. | Keep architecture guard examples aligned with replacement behavior. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS | Documentation builds strictly and the checkpoint diff is whitespace clean after current-truth updates. | Runtime behavior by itself. | Re-run after future docs edits. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 21:51:50 UTC+08:00`; UI unit suite `1137 passed`, real-data IO `31 passed, 8 warnings`. | Fast engineering dashboard remains green after the EvaluationPanel display fix. | Product complete, human Windows acceptance, or long local-model session. | Treat dashboard as health evidence only. |

## 2026-05-13 MCP HTTP Progress Command-State Checkpoint

This headless/MCP slice removed a direct mutable `Study` read from HTTP job progress reporting.
`TrainingStateSnapshot` now carries an optional `progress_message`, populated through the backend
training controller inside the ApplicationService state builder. HTTP MCP job status reads that
snapshot instead of `service.study.trainer`.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red tests: `poetry run pytest --capture=sys tests/unit/mcp/test_http_server.py::test_training_progress_message_uses_application_state_not_study_trainer -q` and `poetry run pytest --capture=sys tests/unit/backend/application/test_state_service.py::test_state_snapshot_service_builds_workflow_snapshot -q` before the fix | Failed as expected: MCP progress read `service.study.trainer`, and state snapshot had no `training.progress_message`. | Reproduced a concrete headless runtime bypass of ApplicationService state truth. | Full MCP client certification or durable job persistence. | Keep HTTP job status state-owned. |
| Same focused tests after the fix | `1 passed` / `1 passed` | MCP progress message can be served from ApplicationService state without reading `service.study.trainer`; state snapshot exposes training progress text. | All job types or long-running training acceptance. | Extend this pattern if evaluation / visualization jobs are added. |
| `poetry run pytest --capture=sys tests/unit/mcp/test_http_server.py tests/unit/mcp/test_server.py tests/unit/backend/application/test_state_service.py -q` | `17 passed` | MCP HTTP/stdio baseline and state query contracts remain green after moving progress truth into ApplicationService state. | External MCP client certification or human desktop acceptance. | Keep transport behavior separated from desktop UI refresh claims. |
| Focused `ruff` / `basedpyright` / `ruff format --check`, plus `poetry run python tests/architecture_compliance.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS / `Architecture compliant!` | Changed MCP/backend state files are lint/type/format clean and keep current architecture guard green. | Product complete. | Run docs/diff before checkpoint commit. |

## 2026-05-13 MCP Direct Study-State Guard Checkpoint

This guard slice locks the MCP progress fix so future product status/progress code cannot
quietly go back to `service.study.trainer`, another mutable `Study` state field, or direct
controller/generator lookup through `service.study`.
Legacy/fallback helpers remain allowed for explicit compatibility boundaries.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| Red test: `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_mcp_direct_study_state_guard_flags_service_study_progress_read -q` before the checker existed | Failed during collection because `check_mcp_direct_study_state_reads` was missing. | Reproduced the missing guard class after removing the concrete MCP progress bypass. | Semantic proof for every MCP function. | Add the checker and keep the sample close to the actual regression. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_mcp_direct_study_state_guard_flags_service_study_progress_read tests/unit/test_architecture_compliance.py::test_mcp_direct_study_state_guard_allows_legacy_helper tests/unit/test_architecture_compliance.py::test_mcp_direct_study_state_guard_flags_service_study_controller_lookup -q` | `3 passed` | The guard rejects direct MCP `service.study.trainer` reads and `service.study.get_controller(...)` bypasses, while allowing explicit legacy/fallback helper boundaries. | External MCP client certification. | Keep adding examples when MCP gains new job/status surfaces. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `91 passed` | Architecture guard unit coverage remains green with MCP direct Study-state and direct Study-method protection included. | Runtime behavior by itself. | Pair guard changes with runtime tests for every removed bypass. |
| Focused `ruff` / `basedpyright` / `ruff format --check`, plus `poetry run python tests/architecture_compliance.py` | PASS / `0 errors, 0 warnings, 0 notes` / PASS / `Architecture compliant!` | The checker and real source tree remain lint/type/format clean and current source has no MCP direct mutable Study-state status/progress violation. | Human desktop acceptance or full MCP certification. | Run docs/diff before checkpoint commit. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 22:29:42 UTC+08:00`; UI unit suite `1137 passed`, real-data IO `31 passed, 8 warnings`. | Fast engineering dashboard remains green after the MCP direct Study-state guard checkpoint. | Product complete, human Windows acceptance, or long local-model session. | Treat dashboard as health evidence only. |

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

## 2026-05-13 UI Refresh Command Truth Checkpoint

| Command | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` | `73 passed`. | Architecture guard unit coverage now proves `main_window.py` direct `study.get_controller(...)` lookup is no longer a blanket exception, while explicit legacy/fallback helpers remain allowed. | Runtime proof that panels no longer need injected controller adapters. | Continue shrinking panel constructor controller dependencies in later slices. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_main_window_sync.py tests/unit/ui/test_legacy_controller_bootstrap.py -q` | `15 passed`. | MainWindow panel construction now routes through `get_legacy_workflow_controllers_for_panel_bootstrap(...)`, and the helper returns a bounded controller bundle or `None` adapters when no getter exists. | Human UI acceptance or proof that read-only panel rendering is fully controller-free. | Add product smoke for stale UI state after command success in the next UI refresh slice. |
| `poetry run python tests/architecture_compliance.py` / focused `ruff` / focused `basedpyright` | `Architecture compliant!` / PASS / `0 errors, 0 warnings, 0 notes`. | The repo is static-clean for the new panel-bootstrap quarantine and the edited guard/test files pass lint/type checks. | Full repo health or runtime flow acceptance. | Keep this gate in branch closure and dashboard validation. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/ui/test_product_walkthrough.py -q` | `4 passed`. | Product-level MainWindow walkthrough now includes an import command-success smoke proving Dataset table refresh uses command/query truth and does not call UI legacy render/sidebar fallback, while the existing import -> preprocess -> epoch -> split -> configure -> dry-run train smoke remains green. | Human Windows desktop acceptance or proof every read-only panel population path is controller-free. | Continue shrinking remaining read-only controller compatibility paths. |
| `poetry run mkdocs build --strict` | PASS with the existing MkDocs Material advisory. | Current architecture docs build after updating the MainWindow bootstrap truth. | File content truth beyond the edited pages or human product acceptance. | Keep docs in sync as remaining read-only population paths are cleaned. |

## 2026-05-13 Real Tools Command Evidence Checkpoint

This slice kept UX work separate: no Data Import UX redesign and no Match Labels / Review and
Import redesign.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_all_real_tools.py tests/integration/pipeline/test_integration_real_tools.py -q` | `15 passed`. | LLM real-tool pipeline tests now assert command-visible state through `QueryStateCommand`, durable backend side effects, and synchronous non-interactive `TrainCommand` evidence instead of direct controller reads or generic non-empty strings. | Human desktop acceptance, GPU training quality, or full external dataset support. | Keep real-tool tests aligned with ApplicationService state snapshots as command results evolve. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/llm/tools/real/test_real_tools.py -q` | `22 passed`. | RealStartTrainingTool preserves the command contract and forwards `confirmed`, `append`, and `interactive` into `TrainCommand`. | Real training runtime by itself. | Keep this paired with at least one integration smoke that observes state side effects. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/ui/test_product_walkthrough.py -q` | `4 passed`. | Product walkthrough still drives user-facing buttons; its dry-run training evidence patches the ApplicationService training command handler and then asserts command/query state, rather than patching `TrainingController.start_training` as product success. | Real long-running training, human Windows click-through, or full zero-controller UI. | Keep a separate human desktop smoke before release claims. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/backend/application/test_training_service.py -q` / `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` | `7 passed` / `8 passed`. | Focused backend ApplicationService and training command-service contracts remain green after the real-tool command parameter pass-through. | Broader backend health beyond these focused suites. | Run broader command-service suites when backend command handlers change. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `73 passed` / `Architecture compliant!`. | Architecture guard examples and static rules still reject known product-success `BackendFacade` / legacy fallback regressions. | Semantic proof outside scanned paths. | Keep adding concrete forbidden examples when a new adapter appears. |
| Weak-evidence scan: `rg -n -i "without crashing|no crash|does_not_crash|crash|len\\(res\\) > 0|isinstance\\(res, str\\)|non-empty|not empty" <real-tools/product-walkthrough tests>`; direct-controller scan: `rg -n "study\\.get_controller\\(|get_controller\\(|TrainingController|BackendFacade|run_legacy_controller_fallback|get_legacy_controller_from_study" <real-tools/product-walkthrough tests>` | Weak-evidence scan has no matches. Direct-controller scan has no product-success controller/fallback use; the only hit is the product walkthrough forbidden-string assertion that `BackendFacade` is not visible to users. | These product-success tests no longer bless controller fallback or no-crash output as success. | Full test-suite quality. | Continue reviewing mock-heavy tests by behavior, not only scan patterns. |
| Focused `poetry run ruff check <changed Python files>` / `poetry run basedpyright <changed Python files>` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed Python files are lint/type clean. | Full repo quality by itself. | Fast dashboard also ran below. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 13:15:27 UTC+08:00`. Includes full ruff, basedpyright, architecture, startup smoke, UI baseline, UI dialog acceptance, UI unit suite, and real-data IO. | Fast engineering dashboard is green after this checkpoint. | Product complete, release approval, or human Windows acceptance. | Human-observable desktop smoke remains required before release claims. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS. | Canonical docs build strictly and the diff has no whitespace errors after this checkpoint record. | Documentation content is automatically complete. | Keep current/architecture/validation records tied to executed commands. |

## 2026-05-13 Product Smoke and Real-Tools Query-Truth Checkpoint

This slice kept UX work separate: no Data Import UX redesign, no Match Labels / Review and
Import redesign, and no answer UI redesign.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/ui/test_product_walkthrough.py tests/integration/ui/test_epoch_runtime.py tests/integration/ui/test_real_tools_e2e.py -q` | `6 passed`. | Guarded UI product smokes and the real-tools UI E2E flow now assert import/preprocess/epoch/split/model/training/evaluation success through `QueryStateCommand`, command diagnostics, command-owned objects, and UI-visible state instead of direct mutable `Study` state reads. | Human Windows desktop acceptance or full zero-controller UI. | Continue migrating remaining product-evidence suites case by case. |
| `MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/pipeline/test_all_real_tools.py tests/integration/pipeline/test_integration_real_tools.py -q` | `15 passed`. | Real-tools integration evidence also stays on ApplicationService / QueryStateCommand state truth after extending the direct-state guard scope. | Human desktop acceptance, GPU training quality, or full external dataset support. | Keep real-tool tests aligned with ApplicationService state snapshots as command results evolve. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `76 passed` / `Architecture compliant!`. | Architecture guard now rejects direct mutable `Study` state reads and `study.get_datasets_generator()` usage in guarded product smokes / real-tools evidence, while existing facade/fallback/UI runtime guards remain green. | Semantic proof outside the guarded files. | Extend guard scope only after replacing existing direct-state setup patterns with command/query evidence. |
| Product-smoke direct-state scan: `rg -n "\\.study\\.(loaded_data_list\|preprocessed_data_list\|epoch_data\|datasets\|dataset_generator\|model_holder\|training_option\|get_datasets_generator)\|\\bstudy\\.(loaded_data_list\|preprocessed_data_list\|epoch_data\|datasets\|dataset_generator\|model_holder\|training_option\|get_datasets_generator)\|loaded_study\\.(loaded_data_list\|preprocessed_data_list\|epoch_data\|datasets\|dataset_generator\|model_holder\|training_option\|get_datasets_generator)" <guarded product-smoke/real-tools tests>` | No matches. | The guarded product smokes no longer use mutable `Study` state as success truth. | Other integration suites that still use direct `Study` state for fixture setup or lower-level pipeline assertions. | Review those suites separately before broadening the guard. |
| Weak-evidence scan: `rg -n -i "without crashing\|no crash\|does_not_crash\|crash\|len\\(res\\) > 0\|isinstance\\(res, str\\)\|non-empty\|not empty" <guarded product-smoke/real-tools tests>` | No matches. | These product smokes do not rely on no-crash wording or generic string evidence. | Full test quality beyond the scanned patterns. | Keep behavior/state assertions as the standard for product evidence. |
| Focused `poetry run ruff check <changed Python files>` / `poetry run basedpyright <changed Python files>` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed Python files are lint/type clean. | Full repo quality by itself. | Fast dashboard also ran below. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 13:52:36 UTC+08:00`. Includes full ruff, basedpyright, architecture, startup smoke, UI baseline, UI dialog acceptance, UI unit suite, and real-data IO. | Fast engineering dashboard is green after this checkpoint. | Product complete, release approval, or human Windows acceptance. | Human-observable desktop smoke remains required before release claims. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS. | Canonical docs build strictly and the diff has no whitespace errors after this checkpoint record. | Runtime behavior. | Re-run after future docs edits. |

## 2026-05-13 UI Integration Controller-Evidence Checkpoint

This slice kept UX work separate: no Data Import UX redesign, no Match Labels / Review and
Import redesign, and no answer UI redesign.

| Command / audit | Result | Claim supported | Claim not supported | Follow-up |
| --- | --- | --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/integration/ui/test_ui_refresh.py tests/integration/ui/test_ui_integration.py tests/integration/ui/test_panel_controller_binding.py -q` | `8 passed`. | UI integration launch/navigation/tab-refresh and TrainingPanel event wiring now use a real empty `Study()` or explicit injected controllers instead of blessing legacy `Study.get_controller()` resolution as success. | Human desktop acceptance, Data Import UX, or full zero-controller UI. | Continue migrating remaining mock-heavy UI integration checks case by case. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_legacy_mock_context_applies_controller_fallback tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_service_success_does_not_read_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_refuses_real_study_controller_fallback -q` | `3 passed`. | TrainingSidebar model selection keeps mock / legacy compatibility while the real service path and real-Study fallback refusal do not read stale controller model-holder truth. | Full TrainingSidebar behavior by itself. | Keep paired service-success and legacy-compatibility tests when shrinking fallback exceptions. |
| `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` / `poetry run python tests/architecture_compliance.py` | `79 passed` / `Architecture compliant!`. | Architecture guard now rejects positive `study.get_controller()` lookup assertions in product-success integration tests and direct `get_model_holder()` missing-result render fallback, while allowing explicit `assert_not_called()` and legacy-helper boundaries. | Semantic proof for every integration test setup pattern. | Keep setup-only mocks separate from product-success assertions. |
| Product-success controller-lookup assertion scan: `rg -n "get_controller\\.(assert_any_call\|assert_called\|assert_called_once\|assert_called_once_with\|assert_called_with)" tests/integration/backend tests/integration/io tests/integration/pipeline tests/integration/ui` | No matches. | Product-success integration suites no longer positive assert direct controller lookup as success evidence. | Controller use inside explicit product bootstrap or mock setup. | Keep positive controller-lookup assertions out of integration/product evidence. |
| Focused `poetry run ruff check <changed Python files>` / `poetry run basedpyright <changed Python files>` | PASS / `0 errors, 0 warnings, 0 notes`. | Changed Python files are lint/type clean. | Full repo quality by itself. | Run broader gates before branch closure. |
| `QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run python scripts/dev/update_quality_dashboard.py` | Dashboard `PASS`, generated `2026-05-13 16:48:26 UTC+08:00`. Includes full ruff, basedpyright, architecture, startup smoke, UI baseline, UI dialog acceptance, UI unit suite, and real-data IO. | Fast engineering dashboard is green after this checkpoint. | Product complete, release approval, or human Windows acceptance. | Keep human-observable desktop smoke separate. |
| `poetry run mkdocs build --strict` / `git diff --check` | PASS / PASS. | Canonical docs build strictly and the diff has no whitespace errors after this checkpoint record. | Documentation readability by itself; readability is judged separately in the final score. | Keep checkpoint records concise so validation history stays readable. |

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
