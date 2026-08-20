# Backend 目前架構

最後更新：`2026-08-13`

## 快速讀法

如果只想知道現在 backend 離 target 多遠，先看這裡；下面的「驗證範圍與歷史脈絡」
保留重構時間線，但不是讀本頁的第一入口。

| 問題 | 目前答案 |
| --- | --- |
| backend 主入口是什麼？ | `ApplicationService / Command API`。UI high-value actions、assistant、headless scripts 都應從這裡進 backend。 |
| `BackendFacade` 還是不是架構的一部分？ | 不是。module 已刪除，architecture guard 會擋 product runtime 和 product-success tests 重新 import / construct。 |
| `ApplicationService` 是不是 god object？ | 已從早期 god-object 形狀拆成 focused services；目前主要負責 dispatch、capability / confirmation gate、state/result envelope。 |
| UI 是否完全不碰 controllers？ | Product MainWindow wiring 不使用 controller bundle；controllers 仍存在於 outer adapters、standalone/mock compatibility 與少數 lower-level utilities。 |
| product success 應該怎麼證明？ | 用 command result、`QueryStateCommand` / state snapshot、typed diagnostics、UI-visible state、exact event/epoch/split/history evidence；不要用 facade、controller compatibility、direct mutable `Study` state、generic non-empty / no-crash assertion。 |
| UI 和 assistant 同時下 command 怎麼辦？ | mutation lock 由 `Study` 擁有，只包 admission / committed-state transition。已遷移的 import、preprocess 與 epoch 重工作先在 detached state 準備，再以 generation / revision / content guard 短暫取得 lock 提交；readers 在 mutation 期間立即回最後一份已驗證 publication。 |
| 長工作如何取消與關閉？ | `OwnedWorkRegistry` 在 command lock 外配置 operation ID，保存 kind / phase / stage / progress 與 cancel intent；UI 的 Cancel、Training Stop 和 close fencing 先走 control path，再由 cooperative checkpoints 或 runtime owner 收斂 terminal receipt。 |

## Current Target Gap

| Area | 已接近 target | 剩餘距離 |
| --- | --- | --- |
| Command spine | load / preprocess / epoch / split specification / training-time materialization / train / evaluate / visualize / saliency / reset / Data Interpretation 都有 command or query truth。 | 要持續防止新 wrapper、direct manager mutation、direct service bypass 回流；retained optional adapters 不是 active roadmap。 |
| Focused services | Data Interpretation、analysis、training、dataset generation、lifecycle、compatibility、data table、preprocess、state/query 都已從 `ApplicationService` 拆出；training resource preview 與 BIDS montage preparation 各有 application-owned coordinator，saliency method policy 由 `backend.application.saliency_policy` 共用。Training preview 使用 service-owned registry，不另建 coordinator-local operation truth。 | focused service 間仍要靠 tests/guard 維持邊界，避免把 orchestration、UI policy 或 controller/context 探測塞回單一檔。 |
| BIDS discovery | `BidsDatasetIndex` 是 formal BIDS root、nested-root resolution、subject catalog、selected recordings 與 sidecar inventory 的共用 immutable source；session cache / process registry 只重用仍 current 的 bounded index。 | 不是 full BIDS inheritance / validator，也不替使用者決定 event/class semantics。 |
| Work ownership | Import review/apply、preprocess、epoch、interactive training、evaluation、explicit saliency 與 render 都可綁一個 backend operation identity；重 CPU/IO preparation 使用 checkpoint，commit 前再驗證 current generation。 | 第三方 loader / model call 內部不一定有細粒度 checkpoint；多資料集真人流程與 Windows native close 尚未完成。 |
| Evaluation / training preview lifecycle | Model Summary 在既有 async `EvaluateCommand` operation 內，對 plan/run collection、input metadata/model construction、input shape、torchinfo/fallback 和 publication 放 cooperative checkpoints。Training preview 對 estimator/model/GPU/batch refinement 使用同一 service registry，identical clients 共用 single-flight operation。 | Cancellation 是 cooperative；未返回的 third-party model、torchinfo 或 GPU query 不能被 Python checkpoint 強制中斷。 |
| State truth | `StateSnapshotService` 建立 snapshot；`ApplicationViewPublication` 原子綁定 snapshot 與 capability policy。一般 `QueryStateCommand(state)`、product UI readers、assistant、headless preflight 共用這個 view。背景 resource / montage 結果只有在 generation 仍 current 時才可更新 publication。 | Refresh single-truth 仍需獨立 exact-commit source guard與 product workflow evidence；少數 lower-level tests 的 direct `Study` access也不能當 product smoke。 |
| Result boundary | Product `CommandResult` 只包含 detached state、changed-state、typed error 與 JSON-safe diagnostics；`runtime` / `local_payload` fields 和 command `include_objects` opt-in 已物理移除。Dataset、Preprocess、training history、Evaluation 與 Visualization 使用 generation-bound detached rows/publications。 | 少數 lower-level presentation utilities 仍直接接收 domain objects；它們不能重新接回 product command result，也不能當 ApplicationService workflow evidence。 |
| UI boundary | Product action method 不可直接呼叫 controller compatibility helper；MainWindow 以 typed ports materialize 五個 panels，Training progress 由 narrow transient port 傳遞。 | Standalone/mock compatibility signatures 仍存在；不是 repo-wide controller removal，refresh exact closure 也需獨立驗證。 |
| Evidence | exact-evidence stack 已替換多個 generic non-empty product smokes。 | human Windows desktop acceptance 和長時間 local-model session 仍缺人工 evidence。 |

## 驗證範圍與歷史脈絡

狀態：`partially-verified`

這份文件已對照目前 source code：

- `XBrainLab/backend/application/*.py`
- `XBrainLab/backend/runtime.py`
- `XBrainLab/backend/study.py`
- `XBrainLab/backend/data_manager.py`
- `XBrainLab/backend/training_manager.py`
- `XBrainLab/backend/controller/*.py`
- `XBrainLab/ui/main_window.py`
- `XBrainLab/llm/tools/real/*.py`
- `XBrainLab/llm/pipeline_state.py`

它描述的是目前程式碼實際狀態，不是理想重構後架構。`ApplicationService`
第一版已落地且完成 command contract 收斂；2026-05-02 第二輪又完成第一批
UI / Agent command surface unification，讓 load / preprocess / epoch / dataset /
train / reset 的 readiness 和 blocked reason 由同一個 capability policy 產生。
本輪再把 UI action execution 擴大接到 `ApplicationService.execute()`：dataset import、
reset / new session、preprocess、channel selection、epoching、split / model / training setting
dialogs、evaluation / visualization / saliency query、training start / stop、metadata update、
smart parse、remove files、label import、montage confirmation。該階段 controller 邊界尚未完整
收斂，但上述 real `Study` mutating paths 已回 `CommandResult`；後續 closure 已將 product
panel construction 移到 typed ports，mock/unit-test compatibility 留在 outer boundary。
2026-05-03 backend hardening 又把
dataset generation 的 apply/audit failure 包成同一個 rollback boundary，避免 datasets /
generator / trainer 半成功殘留；`evaluate` 和 `clear_training_history` 也改成需要真的
training plan history，不能只因 trainer 物件存在就開啟。2026-05-04 Goal 1 第一個
backend slice 又新增 Data Interpretation command baseline，讓 scan / preview / validate /
apply / recipe reload 開始進入同一個 Application Service command spine。後續 Goal 1 slices
已把 Data Interpretation 暴露到 agent tools、Dataset panel 主要 import entry，並新增
`backend.application.automation` 作為 headless JSON adapter；它只轉 command
payload，不新增 controller business logic。最新 architecture cleanup 又把 Data
Interpretation lifecycle state 和 scan / preview / validate / apply / recipe handling 從
`ApplicationService` 拆到 `DataInterpretationCommandService`，並把 reviewed metadata / label
carrier side effects 再拆到 `DataInterpretationApplyService`；`ApplicationService` 現在只保留
command dispatch、capability / confirmation gate、state/result envelope，以及對 focused service
的窄委派。這是 god-object 收斂的連續切片；legacy data / label compatibility path 仍存在，
但不再直接塞在 `ApplicationService`。下一個 cleanup slice 又把 `evaluate`、`visualize`、`saliency` 和
confirmed `apply_montage` 拆到 `AnalysisCommandService`；analysis / visualization readiness
現在也有 focused handler boundary。最新 cleanup slice 又把 `configure_training`、`train`、
`stop_training`、`clear_training_history` 和 reset-time training config clear 拆到
`TrainingCommandService`；model / optimizer / device / training-option snapshot 不再直接留在
`ApplicationService`。最新 dataset cleanup slice 又把 `configure_dataset_split`、`clear_datasets`、
split config、split audit、rollback 和 split summary 拆到 `DatasetGenerationCommandService`。
最新 lifecycle cleanup slice 又把 `reset_preprocess`、`reset_session`、`new_session`、
downstream rollback 和 reset-time dependent-state clear 拆到 `LifecycleCommandService`。
最新 compatibility cleanup slice 又把舊 `load_data`、`attach_labels`、`import_labels` 和
label helper 拆到 `DataCompatibilityCommandService`。最新 data-table cleanup slice 又把
`update_metadata`、`apply_smart_parse` 和 `remove_files` 拆到 `DataTableCommandService`。
最新 preprocess cleanup slice 又把 preprocessing operations 和 `create_epoch` 拆到
`PreprocessCommandService`。最新 state/query cleanup slice 又把 state snapshot assembly 和
`query_state` diagnostics 拆到 `StateSnapshotService` / `QueryStateCommandService`。
`ApplicationService` 仍只 dispatch / gate / wrap result。最新 UI runtime bypass cleanup
也修正 Dataset direct file import 和 Preprocess reset 的 service-success path：real runtime
收到 successful `CommandResult` 後不再落回 controller mutation；controller fallback 僅保留給
mock / compatibility adapter 回傳 `None` 的相容情境。
後續 Training sidebar cleanup 也把重新 split 前的 dataset cleanup 和 Clear History 接回
`ClearDatasetsCommand` / `ClearTrainingHistoryCommand`；successful service result 不再落回
training controller mutation。
2026-05-12 UI fallback helper-scope cleanup 又把 product UI methods 內的直接
`run_controller_compatibility_call()` 呼叫收進 explicit `_compatibility_*` / fallback helpers，並新增
architecture guard：real product method 若直接呼叫 fallback helper 會 fail。這次涵蓋
Dataset actions / panel / sidebar、Preprocess sidebar、Training sidebar、Visualization
control sidebar、AgentManager montage flow、TrainingSettingDialog initial-option fallback。
mock / compatibility `None` adapter branches 仍保留，但它們在程式碼上和 service-backed success path
分離。
最新 command-gate cleanup 又把 capability / confirmation enforcement 從
`ApplicationService._ensure_command_allowed()` 的硬編碼清單抽到
`XBrainLab/backend/application/command_gate.py`。`train` 的 long-running confirmation 現在由
Command API 本身執行：`TrainCommand` 新增 `confirmed` 欄位，未 confirmed 的 backend-ready
training request 會回 `confirmation_required`，而 backend-unready request 仍先回 capability
precondition reason。
最新 Data Interpretation boundary cleanup 把 format capability taxonomy 抽到
`data_interpretation_formats.py`；Data Interpretation lifecycle module 現在呼叫 focused format
boundary helper，而不是同時承接 scanner / candidate / format matrix 細節。
後續 metadata boundary cleanup 又把 metadata resolution、BIDS summary 和 recipe metadata
rehydration 抽到 `data_interpretation_metadata.py`，讓 Data Interpretation lifecycle module 不再
同時承接 metadata parser 細節。
最新 recipe boundary cleanup 又把 `ImportRecipe` serialization / rehydration 和 applied
interpretation -> recipe builder 抽到 `data_interpretation_recipe.py`；lifecycle module 只 re-export
public recipe names for compatibility。
最新 label carrier boundary cleanup 又把 external label carrier planner 抽到
`data_interpretation_label_carriers.py`；Data Interpretation lifecycle module 不再直接承接 CSV /
MAT parser helper 或 label-anchor default selection。
最新 review boundary cleanup 又把 preview payload builder 和 safe / needs-confirmation /
blocked validator 抽到 `data_interpretation_review.py`；Data Interpretation lifecycle module 不再
直接承接 review payload dataclass 或 validation decision construction。
最新 scanner boundary cleanup 又把 source scanning、source kind classification、BIDS root
detection、candidate-file traversal 和 scan warning / blocked reason assembly 抽到
`data_interpretation_scan.py`；Data Interpretation lifecycle module 不再直接承接 scan IO /
source discovery。
最新 candidate boundary cleanup 又把 candidate builder、metadata override、event/class choice
mapping 和 candidate recipe trace 抽到 `data_interpretation_candidate.py`；大型 lifecycle module
基本收斂成 shared enum、applied lifecycle dataclass 和 public compatibility re-export。
最新 session-state boundary cleanup 又把 Data Interpretation lifecycle object stores、latest-id
resolver、snapshot assembly、clear 和 post-load label-import recipe recording 抽到
`data_interpretation_state.py`；`DataInterpretationCommandService` 現在主要保留 command handler
orchestration，state truth 不再混在 handler 檔案裡。
最新 automation schema cleanup 又把 legacy data-entry 降權資訊寫進同一套
`AutomationCommandSpec` truth：`load_data`、`attach_labels`、`import_labels` 的 command spec 和
automation metadata 都會標示 `legacy_compatibility=True`、`primary_workflow=False`，
並列出 Data Interpretation scan / preview / validate / apply / recipe 作為 preferred commands。
這不移除相容工具，但避免 headless client 把它們理解成新資料入口主線。
同一 metadata 現在也暴露 capability-derived `execution` boundary：`long_running`、
`destructive`、`requires_confirmation` 和 `decision_boundary`。
後續 remap schema cleanup 又把 `PreviewInterpretationCommand.choices` schema 抽成
`data_interpretation_choice_schema.py`，agent `preview_interpretation` tool definition、
headless `command_specs()` 共用同一份 `eeg_file_remap` /
`label_carrier_remap` / `label_carrier_choices` / `metadata_overrides` contract。recipe reload
remap 不再只是 UI/backend 私有能力；assistant 和 headless payload 也能走同一個
`preview_interpretation(choices=...)` command truth。

2026-05-11 legacy command spine cleanup removed `BackendFacade` from product runtime
packages. `get_application_service(study)` now owns Study-scoped `ApplicationService`
reuse, and UI capability helpers, AgentManager, LLMController, real agent tools,
and current dev walkthrough scripts enter the backend through
`ApplicationService / Command API` directly. 2026-05-12 physical removal then deleted
`XBrainLab/backend/facade.py` and the facade compatibility-only test files; architecture
compliance now rejects any test that imports or constructs `BackendFacade`.

2026-05-12 zero-legacy runtime cleanup tightened the evidence boundary: product-success
IO and pipeline integration tests now execute `ApplicationService` command sequences
instead of `BackendFacade` or direct `Study.train(...)`, and architecture compliance
rejects `BackendFacade` usage in product-success integration suites. The dataset split
blocker was traced to the Data Splitting dialog defaulting test/validation splitters to
`Disable`; the dialog now defaults both to trial splits and an ApplicationService
regression proves generated train/val/test splits unlock `TRAIN` readiness. `TrainCommand`
also now passes `append` and `interactive` through `TrainingCommandService` to
`TrainingController`, so synchronous test/product smoke training does not bypass the
command contract.

2026-07-11 training-selection hardening separated checkpoint selection from final test
evaluation. `EpochRunner` accepts only train and validation loaders; validation loss,
validation accuracy, validation AUC, or last epoch select the checkpoint. The test loader is
used once only after that choice is fixed. Undefined AUC is represented as `None` and skipped by
best-model tracking rather than being converted to a ranking value of `0.0`. Final `EvalRecord`
also stores whether its data came from test, validation, or training fallback. Saliency settings
may be saved before training, but recomputation is restricted to finished records so it cannot
open the test split before checkpoint selection is complete.

After checkpoint selection, each completed run persists separate inference records for every
non-empty `training`, `validation`, and `test` loader. `EvaluationRenderRequest` binds one exact
plan/run-or-aggregate/split identity. A single run never reads another run's predictions, and an
aggregate is available only when every completed run has the requested split; aggregation pools
only those same-split predictions before computing the existing metrics. The legacy `eval`
artifact remains the primary held-out record for compatibility and saliency, while additional
records use split-qualified artifacts.

2026-07-11 non-blocking view/lifecycle hardening added `ApplicationViewPublication` as the
shared read model for UI, assistant, and headless preflight. A reader opportunistically rebuilds
and atomically publishes state/capabilities when the Study command lock is idle, so background
training completion is visible. If a mutation owns the lock, the reader returns the last verified
generation immediately. Mutable object-bearing queries remain serialized. A mutation is no longer
reported successful when its post-state cannot be verified; the result fails closed and records that
the command effect may already have applied.

Follow-up command-spine hardening on 2026-05-12 fixed three product-runtime contract
gaps. UI command execution now suppresses controller observer-driven refresh while
`ApplicationService.execute(...)` is running, so synchronous controller notifications wait for
the returned `CommandResult.changed_state` refresh scope instead of causing a stale duplicate UI
refresh first. Read-only commands that product UI may call with `refresh=False`
(`QueryStateCommand`, `EvaluateCommand`, `VisualizeCommand`, and no-parameter
`SaliencyCommand`) no longer clear `last_error`, keeping those queries state-preserving.
Unsupported command objects passed to `ApplicationService.execute(...)` now return a structured
`unsupported_command` failure `CommandResult` instead of leaking a raw Python exception. The
architecture guard now also rejects UI code that bypasses `execute_application_command()` by
calling `get_application_service(...).execute(...)` directly.

2026-07-12 pipeline-stage ownership cleanup removed the unused `Study.pipeline_stage` property.
For a real `Study`, `compute_pipeline_stage(...)` now accepts only a caller-supplied
`ApplicationViewPublication`; a missing, invalid, or unknown publication fails closed to `EMPTY`
without importing or calling the application runtime. Direct Study-shaped derivation remains only
for fake / compatibility objects. The preprocess epoch dialog now reads `epoch_handoff` through
`ApplicationUiRuntime.get_view_publication()` instead of inspecting `Study._application_service` or
calling blocking `get_state()`. Architecture compliance protects the private service cache,
`Study -> application.runtime` direction, and the no-service-locator pipeline-stage boundary.

## 一句話架構

XBrainLab backend 目前是以 `Study` 作為中心狀態容器，`DataManager` 和
`TrainingManager` 分別承接資料生命週期與訓練生命週期。Product UI、assistant 和 current
headless scripts 透過 `ApplicationService / Command API` 進入同一個 command layer；controllers
只保留為外層 standalone/test compatibility adapters。

## 實際分層

```text
PyQt product panels
  |
  +--> narrow query / publication / action / transient ports
  |       |
  |       +--> ApplicationService.execute(...) for import / label / metadata / preprocess / epoch / split / query / train / reset / montage
  |       +--> revisioned ApplicationViewPublication for state render
  |       +--> TrainingTransientProgressPort for progress ticks only
  |
  v
Study
  |
  +-- DataManager
  |     +-- loaded_data_list
  |     +-- preprocessed_data_list
  |     +-- epoch_data
  |     +-- datasets
  |
  +-- TrainingManager
        +-- model_holder
        +-- training_option
        +-- trainer
        +-- saliency_params

Assistant real tools / headless scripts
  |
  v
ApplicationService / Command API
  |
  +--> DataInterpretationCommandService
  |       +--> scanner / candidate builder / review service / recipe state
  |       +--> DataInterpretationSessionState for lifecycle stores / snapshot truth
  |       +--> DataInterpretationApplyService
  |               +--> reviewed metadata apply / reviewed label carrier apply
  |
  +--> AnalysisCommandService
  |       +--> evaluation summary / visualization readiness / saliency setup / montage apply
  |
  +--> TrainingCommandService
  |       +--> model config / training option config / train-stop lifecycle / history cleanup
  |
  +--> DatasetGenerationCommandService
  |       +--> saved split specification / deferred materialization / split audit / rollback / dataset cleanup
  |
  +--> LifecycleCommandService
  |       +--> reset preprocess / reset session / new session / dependent-state cleanup
  |
  +--> DataCompatibilityCommandService
  |       +--> legacy load_data / attach_labels / import_labels compatibility
  |
  +--> DataTableCommandService
  |       +--> metadata update / smart parse / remove files
  |
  +--> PreprocessCommandService
  |       +--> preprocessing operations / create_epoch
  |
  +--> StateSnapshotService / QueryStateCommandService
          +--> state snapshot assembly / query_state diagnostics
  |
  v
Study-owned manager/domain ports
plus detached TrainingProjectionReadPort for Evaluation catalog/render

Headless automation
  |
  v
backend.application.automation
  |
  v
ApplicationService.execute(...)

UI / Agent readiness decisions
  |
  v
ApplicationService.get_capabilities()
```

## 入口判斷

### UI 入口

UI 不是透過 `BackendFacade` 操作 backend。

`XBrainLab/ui/main_window.py` 以 typed ports materialize 五個 product panels，不再建立或注入
compatibility controller bundle。Dataset / Preprocess 使用 application publication/query port；
Training 使用 query、publication、action 和 transient-progress ports；Evaluation /
Visualization 使用 detached query/publication/action ports。State-changing render 由
revisioned publication 提交，Training transient port 只承載 progress tick。

Controllers 仍存在於 standalone/test compatibility constructors 和外層 adapters，但 real
`Study` product context 若缺少 typed publication/capability 必須 fail closed，不可自行回到
controller tree。這些殘留是後續 P2 cleanup，不是 product action、readiness 或 render truth。

第一批 UI-facing decision 已改讀 ApplicationService capability policy：

- Dataset import readiness 先讀 `load_data` capability，blocked reason 由 backend policy 產生。
- Preprocess sidebar 的 filtering / resample / rereference / normalize readiness 先讀
  `preprocess` capability。
- Epoching readiness 先讀 `create_epoch` capability。
- Training sidebar 的 Start Training enabled / tooltip / click-time guard 先讀 `train`
  capability，不再自己重寫一套 dataset/model/training option 判斷。
- Chat panel / AgentManager 的 compact backend diagnostics，以及 Preprocess epoch dialog 的
  `epoch_handoff`，都讀同一份 `ApplicationViewPublication`；UI helper 不自行拼接 state / capability
  或檢查 private service cache。

同一批 high-value execution 也已接 service-backed command adapter：

- Dataset import 使用 `LoadDataCommand`。
- Dataset direct file import 的 successful `LoadDataCommand` path 不再再呼叫
  `DatasetController.import_files()`；controller import 只保留給 command adapter 不存在的
  mock / compatibility `None` fallback。
- Dataset clear / reset 使用 `ResetSessionCommand(confirmed=True)`。
- Preprocess filtering / resample / rereference / normalize 使用 `PreprocessCommand`。
- Preprocess reset 使用 `ResetPreprocessCommand(confirmed=True)`；successful service result 不再
  落回 `PreprocessController.reset_preprocess()`。
- Channel selection 使用 `PreprocessCommand(SELECT_CHANNELS)`。
- Epoching 使用 `CreateEpochCommand`。
- Split / model / training setting dialog submit 使用 `SaveDatasetSplitCommand` /
  `ConfigureTrainingCommand`。
- Re-split 前清 datasets 使用 `ClearDatasetsCommand(confirmed=True)`；Clear History 會先做
  user confirmation，再使用 `ClearTrainingHistoryCommand(confirmed=True)`。
- Evaluation / visualization / saliency query 使用 `EvaluateCommand` /
  `VisualizeCommand` / `SaliencyCommand`。
- Training start / stop 使用 `TrainCommand` / `StopTrainingCommand`。
- New session 使用 `NewSessionCommand`，有 state 時仍受 confirmation policy 管控。
- Metadata table edit / batch edit 使用 `UpdateMetadataCommand`。
- Smart parse 使用 `ApplySmartParseCommand`。
- Remove files 使用 `RemoveFilesCommand`。
- Label import dialog 使用 `ImportLabelsCommand(LabelImportPlan(...))`。
- Agent montage confirmation 使用 `ApplyMontageCommand`。
- Info panel state refresh 使用 `QueryStateCommand(data_lists)`。

UI 測試中的 mock `Study` 仍走 explicit controller compatibility，避免 unit test 用不完整 mock state
誤觸真 ApplicationService policy。architecture guard 現在要求這些 fallback 只能出現在
明確的 legacy / fallback helper，不可藏在 product action method 裡；MainWindow 的 panel
bootstrap controller lookup 也只允許透過 named quarantine helper。

仍保留 controller / UI-request path 包含：

- mock / unit-test compatibility fallback。
- montage picker 的 human-in-the-loop UI request；真正 apply 已走 `ApplyMontageCommand`。
- panel read-only refresh / population，例如 tables、plots、combo box contents。

### Assistant / headless 入口

Assistant real tools、LLMController 和 dev walkthrough scripts 現在直接使用
`get_application_service(study)` 或自己持有的 `ApplicationService` session。
`BackendFacade` 不再存在；assistant / headless 入口不保留舊方法名稱或舊回傳形狀。

`XBrainLab.backend.application.automation` 是 headless adapter。它輸出
`ApplicationService` command schema 和 live capability / autonomy
policy，並將 JSON payload 驗證後轉成 typed command 再呼叫 `ApplicationService.execute()`。
同一個 schema 也會標出 legacy compatibility boundary：`load_data`、`attach_labels`、
`import_labels` 仍可呼叫，但 metadata 明確標為非 primary workflow，並提供 Data Interpretation
preferred commands。

Historical boundary: MCP stdio／HTTP package、schema projection、CLI、capture與tests已從executable
source退役；舊transport provenance只存在Git history。任何未來adapter都需要新的public
contract／security decision，且仍必須delegate through
`backend.application.automation`／`ApplicationService`，不得建立第二份state、capability或workflow truth。

`ApplicationService` 現在直接組合同一個 `Study` 擁有的 focused product ports：

- `dataset_state_service`
- `preprocess_state_service`
- `training_state_service`
- `visualization_state_service`

`Study.get_controller(...)` 的 cached registry 仍保留給 outer adapter、standalone/mock compatibility
與尚未移除的低階入口，但不是 `ApplicationService` product dependency。

Evaluation 是明確例外：product path 不建立 `EvaluationControllerAdapter`，而是由
`TrainingProjectionReadPort` 產生 serializable catalog、generation-bound detached render
publication 與 model summary。`Study.get_controller("evaluation")` 仍是 legacy controller
registry 的 compatibility surface，不是 ApplicationService dependency。

`XBrainLab/llm/tools/real/dataset_real.py`、`preprocess_real.py`、`training_real.py` 和
`analysis_real.py` 也已改成 command-backed real tools。Mapped workflow tools 由
`LLMController` 透過 `execute_application_tool_command(...)` 直接執行 ApplicationService
command 並回傳 `ToolCommandResult.from_command_result(...)`；read-only tools 也從 command
query result 取得 state truth。

結論：`BackendFacade` module 已物理移除，不能再被描述成 non-product wrapper、
compatibility target 或 agent/tool runtime 入口。新邏輯應進 `ApplicationService` 下的
focused command service / handler；UI 目前仍是 service-first migration 的中間狀態，
尚未完整完成。

### Data Interpretation command baseline

2026-05-04 第一個 Goal 1 backend slice 新增：

- `XBrainLab/backend/application/data_interpretation.py`
- `ScanSourceCommand`
- `PreviewInterpretationCommand`
- `ValidateInterpretationCommand`
- `ApplyInterpretationCommand`
- `SaveInterpretationRecipeCommand`
- `ReloadInterpretationRecipeCommand`

這批 command 由 `ApplicationService` dispatch / gate，實作與 in-memory lifecycle state
目前位在 `DataInterpretationCommandService`，並回傳 typed diagnostics：

- `ScanResult`：掃描 file / folder / BIDS-EEG source / recipe，列出 EEG files、label
  carriers、BIDS summary 和 subject / session / task / run metadata provenance。
- `InterpretationCandidate`：根據 scan result 和 optional choices 建立候選解讀。
- `InterpretationPreview`：提供 file count、label carrier count、metadata preview、
  warnings、confirmation items 和 downstream impact。
- `ValidationDecision`：只使用 `safe`、`needs_confirmation`、`blocked`，不使用不可審查的
  confidence score。
- `AppliedInterpretation`：確認後呼叫既有 dataset import path 載入 selected EEG files，
  並記錄 label carriers / metadata / confirmations / recipe trace。
- `ImportRecipe`：可寫成 JSON；reload recipe 會重新 scan / preview / validate，不會直接 apply。

`ApplicationStateSnapshot` 現在包含 `interpretation` section，`CapabilityPolicy` 也包含
Data Interpretation commands 的 `can_auto_execute`、`requires_confirmation`、
`decision_boundary`、`continue_allowed_after_success`、`retry_limit`、`stop_after_success`、
`blocks_downstream_until_confirmed` 等 autonomy 欄位。UI import wizard 與 agent tool
taxonomy 都以這套 Data Interpretation command sequence 作為產品資料入口。

### Reviewed data / training decision contracts

目前 working candidate 把下游設定綁回 reviewed import 與 backend-owned provenance：

- `BidsDatasetIndex` 對明確選取的 formal BIDS root 做一次 bounded walk，解析 nested root，
  建立 subject catalog、selected-subject projection、recording entities 和 events / channels /
  electrodes / coordsystem / JSON sidecar inventory；scan、review、apply、EEGLAB dependency preflight
  與 montage preparation 只接受仍 current 的 index。
- Small JSON / CSV / TSV parsing 由 `ParsedContentCache` 以 complete source bytes SHA-256、
  parser ID、schema version 和 value kind 綁定 immutable result。LRU 同時限制 entries、retained
  bytes 與單檔 bytes；Windows path binding 不以 `ctime` 當 freshness 證據。
- BIDS label-field recommendation 由 `data_interpretation_label_carriers.py` 聚合 selected
  `events.tsv` runs 的 bounded row profiles、欄位 coverage、sidecar `Levels`、observed values 與
  cross-run consistency。任一 selected table 的 row / byte inspection 被截斷，或 evidence 不足時，
  都不產生自動推薦；explicit selection 優先，recommendation 仍須由使用者 review。
- `epoch_context.py` 只在每段 recording timing hint 可讀、reviewed `epoch_handoff` 可用，且 label
  source / placement 相符時發布 available context。任何缺漏、malformed payload、hint read failure
  或 mismatch 都 fail closed。Duration / event-locked mode 來自 handoff 綁定的 applied timing
  evidence；dialog 不建立第二套 fallback truth。
- `SaveDatasetSplitCommand` 只保存 typed specification、epoch revision、fingerprint 與 preview
  receipt。`TrainCommand` 才要求 `DatasetGenerationCommandService` materialize masks、執行 leakage /
  coverage audit，再進 resource preflight；失敗時保留先前 dataset / trainer / training state。
- `TrainingRecommendationService` 依 detached epoch shape、split summary、selected model family 和
  device metadata 產生 deterministic conservative defaults。`training_submission.py` 只接受 trusted
  host 附加 per-field edited provenance，重新推薦時只保留這些 manual fields。
- Import discovery/apply、preprocess 與 epoch 的 heavy IO / copy / MNE construction 在 detached
  preparation 執行；短 commit boundary 重新驗證 session generation、source identity、revision /
  fingerprint 與 cancel intent，失敗或 stale 時保留原 committed state。
- Training terminal path 只發布 metrics。只有 explicit `SaliencyCommand`（由 visible
  `Compute Saliency` action 觸發）才建立 exact completed-run target 並排程 attribution；
  generation 或 producer identity 不符的結果不得發布。
- Timed hyperparameter search、trial orchestration、pruning 和 automatic model selection 沒有
  command / service / tool contract；它們只在 roadmap，不能從 recommended-defaults surface 推論
  已實作。

### Agent command surface

Agent 現在不再只靠 `pipeline_state.py` 的 stage table 決定工具可用性。

新增 `XBrainLab/llm/tools/application_surface.py`，將 agent tool names 對映到
ApplicationService command names：

| Agent tool | Application command |
| --- | --- |
| `load_data` | disabled legacy compatibility surface; use Data Interpretation |
| `attach_labels` | `attach_labels` |
| `apply_standard_preprocess` / `apply_bandpass_filter` / `apply_notch_filter` / `resample_data` / `normalize_data` / `set_reference` / `select_channels` | `preprocess` |
| `set_montage` | `apply_montage` capability + UI confirmation request |
| `epoch_data` | `create_epoch` |
| `configure_dataset_split` | `configure_dataset_split` |
| `set_model` / `configure_training` | `configure_training` |
| `start_training` | `train` |

`list_files`、`get_dataset_info`、`switch_panel` 是 read-only / UI routing tools；
其中 `get_dataset_info` 會依 state 判斷是否已有 raw data。

`ContextAssembler` 現在使用 ApplicationService policy 決定可列出的 tools，並在 prompt
中放 blocked command reason。`LLMController._execute_tool_no_loop()` 在真正執行前也會
重新讀 capability policy；因此 prompt 與 execution guard 使用同一個 backend policy。

tool execution 後寫回 conversation history 的 `Tool Output` 已改為結構化 JSON payload：
`ok`、`tool_name`、`message`、`raw_result`。UI side effects 仍暫時保留 `Request:` 字串
協定，後續要改成 typed request。

2026-05-02 product audit follow-up 後，這個 structured `Tool Output` 不再直接進第一層
ChatPanel transcript。`LLMController` 會把 `ToolCommandResult` 轉成產品語言：missing folder
會要求使用者提供 folder/path，empty file list 會顯示空狀態，backend precondition 會顯示
可修正的 blocked reason。raw schema error、Python list、tool name、backend command name、
snake_case command 只留在 history / diagnostics / logs。

Mapped agent workflow tools 會優先直接執行 ApplicationService command，包含
Data Interpretation、`attach_labels`、preprocess tools、`epoch_data`、
`configure_dataset_split`、`set_model`、`configure_training`、`start_training`。
舊 `load_data` tool definition 只保留 compatibility identity；產品 policy 與 executor
一律 fail closed，要求改走 `scan_source -> preview_interpretation ->
validate_interpretation -> apply_interpretation`。這避免把 identity-bound 授權目錄重新
展開成普通字串後再開檔。`set_montage` 和
`switch_panel` 仍是 UI request path；`set_montage` 的 capability 由 `apply_montage` policy
決定，confirmation 後的 apply 走 `ApplyMontageCommand`。`list_files` / `get_dataset_info`
仍是 read-only / inspection tools，但現在也會經 typed result normalization，避免 legacy
`"Error: ..."` 或 `[]` 被誤當成功 visible response。

### Script / headless path

Headless script 應使用 `ApplicationService`、`get_application_service(study)`，或
`backend.application.automation.execute_automation_payload()`。不要在 script 裡直接重建
readiness 判斷；需要狀態或 blocked reason 時使用 `ApplicationService.get_state()` /
`get_capabilities()`。

### Application Service / Command API

第一版位置：

- `XBrainLab/backend/application/commands.py`
- `XBrainLab/backend/application/analysis_service.py`
- `XBrainLab/backend/application/state.py`
- `XBrainLab/backend/application/capabilities.py`
- `XBrainLab/backend/application/data_compatibility_service.py`
- `XBrainLab/backend/application/data_interpretation.py`
- `XBrainLab/backend/application/data_interpretation_apply.py`
- `XBrainLab/backend/application/data_interpretation_candidate.py`
- `XBrainLab/backend/application/data_interpretation_formats.py`
- `XBrainLab/backend/application/data_interpretation_label_carriers.py`
- `XBrainLab/backend/application/data_interpretation_metadata.py`
- `XBrainLab/backend/application/data_interpretation_recipe.py`
- `XBrainLab/backend/application/data_interpretation_review.py`
- `XBrainLab/backend/application/data_interpretation_scan.py`
- `XBrainLab/backend/application/data_interpretation_service.py`
- `XBrainLab/backend/application/data_table_service.py`
- `XBrainLab/backend/application/dataset_generation_service.py`
- `XBrainLab/backend/application/lifecycle_service.py`
- `XBrainLab/backend/application/preprocess_service.py`
- `XBrainLab/backend/application/results.py`
- `XBrainLab/backend/application/state_service.py`
- `XBrainLab/backend/application/training_service.py`
- `XBrainLab/backend/application/errors.py`
- `XBrainLab/backend/application/service.py`

目前已提供：

- `ApplicationService.get_state()`：委派 `StateSnapshotService` 回傳可序列化 state snapshot，包含
  raw/preprocessed/epoch/dataset/training/evaluation/visualization、active dataset /
  training、interpretation、`last_error` 和 diagnostics。
- `ApplicationService.get_capabilities()`：由 backend state 產生 capability policy，
  阻擋缺前置條件的 command，例如沒有 raw data 不能 preprocess、epoch/dataset 後不能
  一般性 `load_data`、沒有 dataset/model/training option 不能 train。
- `ApplicationService.get_view_publication()`：原子回傳同一 generation 的 state 與 capability；
  command lock 空閒時先刷新，lock 忙碌時不等待並回最後一份已驗證 publication。
- `ApplicationService.execute(command)`：回傳 `CommandResult`，包含
  status、command name、message、changed state、error type、recoverable 和 diagnostics。
- `begin_owned_operation(command)` / `execute(..., operation_id=...)`：
  先配置 lock-independent identity，再以 exact command kind / identity single-claim 執行；
  terminal replay、kind mismatch 或 command mismatch 會 fail closed。
- `cancel_owned_operation(operation_id)` / `get_owned_operation(operation_id)`：
  不取得 shared command lock 即可送出 cancel intent 與讀取 immutable snapshot。Training /
  Saliency 另把 cancel 轉交其 native runtime owner；其他流程在 bounded checkpoints 回應。
- 已接上的核心 commands：
  `scan_source`、`preview_interpretation`、`validate_interpretation`、
  `apply_interpretation`、`save_interpretation_recipe`、`reload_interpretation_recipe`、
  `load_data`、`attach_labels`、`import_labels`、`update_metadata`、`apply_smart_parse`、
  `remove_files`、preprocess operations、`create_epoch`、`configure_dataset_split`、
  `clear_datasets`、`configure_training`、`train`、`stop_training`、
  `clear_training_history`、`apply_montage`、`reset_preprocess`、`reset_session`、
  `new_session`。
- service-backed query / setup commands：
  `evaluate`、`visualize`、`saliency`、`query_state`。它們回傳 typed summary diagnostics；
  `saliency` 也能設定 saliency params。
- `evaluate`、`visualize`、`saliency` 和 confirmed `apply_montage` 的 handler 實作位置現在是
  `AnalysisCommandService`。
- State snapshot assembly 和 `query_state` diagnostics 的實作位置現在是
  `StateSnapshotService` / `QueryStateCommandService`。`ApplicationService` 仍提供
  strict/fresh `get_state()` / `get_capabilities()` 給 command 內部驗證；一般 state query 與
  product read surface 使用 publication，避免長 mutation 卡住 GUI。
- `configure_training`、`train`、`stop_training`、`clear_training_history` 和 reset-time
  training config clear 的 handler 實作位置現在是 `TrainingCommandService`。它 owns model
  holder 建立、optimizer / device / evaluation option resolve、training option snapshot 和
  training lifecycle notification；`ApplicationService` 只做 dispatch、policy gate 和 result
  envelope。
- `train` 的 long-running confirmation 由 `command_gate.py` 在 `ApplicationService.execute()`
  前檢查；UI / agent / headless adapter 只有在人類確認後才傳 `TrainCommand(confirmed=True)`。
- UI Training sidebar 的 Clear History action 會透過 `ClearTrainingHistoryCommand` 進入
  `TrainingCommandService`；只有 mock / compatibility `None` adapter 情境才回到 controller fallback。
- `configure_dataset_split`、deferred split materialization、`clear_datasets`、split audit、rollback
  和 `DatasetStateSnapshot` 的 split lifecycle / summary 實作位置現在是
  `DatasetGenerationCommandService`。Confirm 只保存 specification；`train` 才準備並驗證 candidate。
  `ApplicationService` 的 reset preprocess rollback 只委派到這個 service 的 state restore
  helper，不再自己操作 dataset generator / trainer rollback 細節。
- UI Training sidebar 重新 split 前的 destructive dataset cleanup 會透過
  `ClearDatasetsCommand` 進入 `DatasetGenerationCommandService`；successful service result 不再
  落回 `TrainingController.clean_datasets()`。
- `reset_preprocess`、`reset_session`、`new_session`、downstream rollback 和 reset-time
  dependent-state clear 的實作位置現在是 `LifecycleCommandService`。它會委派到
  `DatasetGenerationCommandService` 和 `TrainingCommandService`，避免 reset path 在
  `ApplicationService` 裡重建第二套 lifecycle truth。
- 舊 `load_data`、`attach_labels`、`import_labels` 和 label helper 的實作位置現在是
  `DataCompatibilityCommandService`。它明確是 compatibility boundary；新 Data
  Interpretation 主線仍應走 `DataInterpretationCommandService`。
- `update_metadata`、`apply_smart_parse` 和 `remove_files` 的實作位置現在是
  `DataTableCommandService`。它 owns loaded-data table mutation diagnostics；`ApplicationService`
  只做 dispatch、policy gate 和 result envelope。
- Preprocessing operations 和 `create_epoch` 的實作位置現在是 `PreprocessCommandService`。
  它 owns preprocess controller calls、standard batch preprocessing、channel selection delegate
  和 `set_montage` UI confirmation boundary。
- UI Preprocess reset action 會透過 `ResetPreprocessCommand` 進入 lifecycle service；只有
  `execute_application_command()` 回傳 `None` 的 mock / compatibility adapter 情境才回到 controller
  fallback。
- Data Interpretation command handlers 實作位置現在是
  `DataInterpretationCommandService`。它 orchestration scan / preview / validate / apply /
  recipe commands；scan/candidate/preview/validation/applied/recipe in-memory state、latest-id
  resolver、snapshot 和 recipe label import state 更新在 `DataInterpretationSessionState`；
  reviewed metadata apply 與 reviewed label carrier apply 則在 `DataInterpretationApplyService`。
  `ApplicationService` 不再直接承接這些 workflow 細節。
- `apply_interpretation` capability 也會套用 raw-edit blockers；若 active session 已有 epoch、
  generated dataset、trainer 或 locked raw data，UI / agent 必須先 reset / new session，
  不能把新的 Data Interpretation 直接套進既有 downstream pipeline。
- Data Interpretation format capability matrix 實作位置現在是
  `data_interpretation_formats.py`。它 owns GDF、EDF / BDF、EEGLAB、BrainVision、FIF、MAT、
  CSV / TSV、TXT、BIDS events 和 XDF / LSL 的 supported / needs-review / blocked 邊界。
- Data Interpretation metadata resolution 實作位置現在是
  `data_interpretation_metadata.py`。它 owns subject / session / task / run field resolution、
  BIDS entity aggregation、filename-rule confirmation boundary 和 recipe metadata rehydration。
- Data Interpretation recipe serialization 實作位置現在是
  `data_interpretation_recipe.py`。它 owns `ImportRecipe`、JSON load / write、serialized metadata
  rehydration 和 applied interpretation to recipe conversion；`data_interpretation.py` 只 re-export
  public names so existing service / application imports remain stable。
- Data Interpretation label carrier planner 實作位置現在是
  `data_interpretation_label_carriers.py`。它 owns label carrier choice normalization、MAT variable
  discovery、CSV / TSV / BIDS events column discovery、anchor candidates、time model defaults、
  granularity defaults 和 review reason generation。
- Data Interpretation review payload / validator 實作位置現在是
  `data_interpretation_review.py`。它 owns `InterpretationPreview` / `ValidationDecision`、
  candidate-to-preview serialization，以及 safe / needs-confirmation / blocked decision boundary。
- Data Interpretation scanner 實作位置現在是 `data_interpretation_scan.py`。它 owns
  `ScanResult`、source path scanning、source kind classification、BIDS root detection、candidate
  file traversal、label carrier discovery、scan warnings 和 blocked reason assembly。
- Data Interpretation candidate builder 實作位置現在是 `data_interpretation_candidate.py`。它
  owns `InterpretationCandidate`、scan + user choices to candidate conversion、metadata overrides、
  event/class mapping、label-carrier choice trace 和 candidate recipe trace。

2026-05-02 product blocker 盤點結論：

- `hello` no-response 問題主要發生在 chat / agent visible-output boundary，不是
  `ApplicationService` command contract 本身。
- `ApplicationService` / `CapabilityPolicy` 仍是 UI / Agent shared decision 的正確入口。
- `ApplicationService` 仍是 command spine，但不應重新吸收 workflow logic；新增 workflow 應
  優先放在 focused command service / handler，再由 `ApplicationService.execute()` 統一 gate
  與包 result。
- backend query command 已從 future placeholder 推進成 service-backed summary / setup
  result；完整 interactive evaluation / visualization workflow 仍要由 UI walkthrough 驗收。
- `evaluate` / `clear_training_history` capability 以 actual training plan history 為準；
  trainer object 存在但 history 已清空時不再啟用這兩個 command。
- training-time split materialization 和 audit 共用 rollback boundary；audit blocking issue
  或 apply 中途例外都不應覆寫既有 datasets / dataset generator / trainer。
- error boundary 對 command result 已足夠支撐 UI 顯示 blocked reason；UI / agent 必須把它
  轉成 visible user feedback，而不是只記在 diagnostics。

### Training artifact filesystem boundary

Training/evaluation persistence 只透過
`XBrainLab/backend/training/record/artifact_store.py` 寫入或讀取 versioned JSON manifest、
non-pickle NPZ 與 tensor-only checkpoint。`filesystem_identity.py` 在一次 bounded artifact IO
期間保留 output directory identity；POSIX leaf access 使用 directory-descriptor-relative
`O_NOFOLLOW` / exclusive create，Windows leaf access 使用 native reparse-point handle。兩個平台
都拒絕 non-regular entry 與多重 hardlink，publication 使用同一 retained parent identity 內的
atomic replace。這個 contract 防止 artifact leaf substitution，但不能取代真人 NTFS
junction/reparse acceptance；使用者另外選取的 pretrained weight 與 source EEG reader 屬各自的
admission boundary，不應被誤稱為 training artifact persistence。

### Public diagnostic / log privacy boundary

`XBrainLab/backend/utils/public_diagnostics.py` 是 logs、exception/result messages、assistant
feedback 與 UI interaction outcomes 的共同 privacy boundary。預設 `PUBLIC` disclosure：

- 完整 POSIX / Windows / UNC 私人路徑只保留可辨識的 basename（若其中有 BIDS / subject token
  會再遮罩）和 `[PATH_REF:...]`；parent directories 不進 log 或 user-visible message。
- `subject_id` / `participant` / `patient` 與 BIDS `sub-*` 會變成 `[SUBJECT_REF:...]`。reference
  使用 process-local random HMAC key，同一 app process 內穩定，restart 後刻意不可關聯，也不能
  從低熵 subject id 反查原值。
- NUL、ANSI escape、Unicode format/control characters 會在輸出前移除或壓成空白。default
  logs、developer detail 與 compact status event 強制使用 `SINGLE_LINE`，避免 exception /
  dataset metadata 製造額外 log lines；rich presentation 只允許 normalized LF，CR 和其他
  control characters 不會保留。
- `CommandResult.message` / `error_message`、`ApplicationError` / `XBrainLabError`、
  `InteractionOutcome`、assistant delivery/result/presentation 都走這個 boundary。原始
  `CommandResult.diagnostics` 仍保留在 process 內供 UI workflow 使用，不以刪資料方式換取
  privacy。
- `CommandResult.to_dict()` 是 local functional adapter contract，不能當公開 diagnostics；
  export / support output 必須用 `CommandResult.to_public_dict()`。Agent 對 model/history 的
  `ToolCommandResult.to_payload()` 也會做 recursive public projection。
- default `XBrainLab` rotating file / console handlers 在 record 傳給其他 handler 前 redaction，
  exception traceback 也只保留 safe basename、line / exception type 與已遮罩 detail。source
  guard 禁止 product modules 另裝 `FileHandler` / `StreamHandler` 或設 `propagate=False` 繞過
  central handler。

Detailed diagnostics 不是 settings 或 UI toggle。只有受控診斷程式碼明確傳入
`DiagnosticDisclosure.DETAILED` 才可開啟；這個 mode 仍套用相同 layout/control policy 並移除
credentials 與 email，但可能保存完整 private path / subject identifier。使用政策是
local-only、最短必要時間、使用者審閱與同意後才可分享，完成診斷後刪除，不可自動上傳。

Default retention 是 active `5 MiB` 加 `5` 個 rotating backups（nominal upper bound 約
`30 MiB`）。POSIX log directory / file 每次建立或 reopen 都驗證為目前使用者擁有的
`0700` / `0600`。Windows 以同一個 opened file object 套用並 read-back 驗證 protected DACL：
目錄只有目前使用者的 inheritable full-control ACE，active log、marker 與每個 rotating backup
只有目前使用者的 non-inheritable full-control ACE。任何 Win32 API、owner、DACL、ACE、reparse
point 或 read-back 驗證失敗都會停用 file sink，只保留已遮罩的 console logging。

Windows ACL boundary 不宣稱能限制 Administrator / SYSTEM、同帳號惡意程式，或取代 ancestor
junction race 的 SEC-06 containment gate。Packaged launcher、非 NTFS volume 與第二個標準帳號的
實際拒絕測試仍屬 Windows acceptance。Detailed log 不可放到 shared / network location。

UI source guard 會拒絕 catch-all exception 或 worker callback error 直接進
`QMessageBox` / status sink；unexpected error 只顯示穩定可操作文案，完整 exception 先經
central public-diagnostic boundary 後才可寫入 default diagnostics。少數 mock-only controller
compatibility path 顯示的是固定的 public unavailable message，不是 backend exception detail。

重要邊界：

- product command 透過 `Study`-owned focused services / domain ports 執行；controller registry 僅是
  outer adapter、standalone/mock compatibility 與少數尚待收斂的低階入口。
- Data Interpretation 的 lifecycle truth 目前在 `DataInterpretationSessionState`，並由
  `DataInterpretationCommandService` 作為 command boundary 協調；UI、agent 和
  automation 仍必須透過 `ApplicationService.execute()` 進入，不可直接建立第二套
  interpretation state。
- Analysis / visualization readiness truth 目前在 `AnalysisCommandService`，但 capability
  exposure 仍由 `ApplicationService.get_capabilities()` 產生。
- `BackendFacade` module 已物理移除；product runtime、tests 和文件都不得把它恢復成
  wrapper、compatibility target 或可 instantiate 的 abstraction。
- `get_application_service(study)` 會重用掛在同一個 `Study` 上的 `ApplicationService`。這是
  Data Interpretation lifecycle 的必要邊界，否則 `scan_source` 產生的 scan state 會在下一個
  `preview_interpretation` tool call 因重新建立 service 而遺失。
- `application_surface.py` 是 agent tool-name 與 ApplicationService command-name 的 adapter；
  read-only / compatibility tools 必須回到 command query / typed formatter，不可讓 legacy string
  result 直接進 transcript。
- `set_montage` 仍是 UI confirmation request path；agent tool 的 availability 讀
  `apply_montage` capability，confirmation 後由 `ApplyMontageCommand` 實際寫入 channel
  positions。
- `reset_session` 仍是 internal backend lifecycle command；它目前代表清掉 active backend
  session：raw / preprocess / epoch / dataset / trainer / model option / saliency config 都會失效。
  Desktop UI 與 Assistant 不發布這個操作，automation / internal integration 仍可直接使用 typed
  command。
- `new_session` 目前是同一個 single-backend session 的 lifecycle boundary，不是 multi-document
  project shell；它清掉目前 state 後回傳 `single_session_backend=True` diagnostics。

## 核心物件責任

### Study

`Study` 是中心 state container 和 controller factory。

目前責任：

- 建立 `DataManager`。
- 建立 `TrainingManager`。
- 快取 controllers，確保同一個 `Study` 內 controller 是 singleton-like。
- 提供舊屬性相容層，例如 `study.loaded_data_list` 實際委派到 `study.data_manager.loaded_data_list`。
- 提供清理 cascade，例如清 raw data 時也清 datasets / trainer。
- 擁有 application service cache slot 與 command lock；service/runtime lifecycle owner 負責讀寫
  cache。`Study` 本身不 import application runtime，也不暴露 `pipeline_stage` property。

重要判斷：`Study` 仍是新舊架構混合點。它已經把資料與訓練狀態拆給 manager，但仍保留大量 delegation property 來維持 UI 和 tests 相容。

### DataManager

`DataManager` 管資料生命週期。

目前責任：

- raw data list
- preprocessed data list
- epoch data
- generated datasets
- dataset generator
- dataset lock / unlock
- loaded data backup
- preprocess reset
- dataset cleanup

重要行為：

- `set_loaded_data_list()` 會同步建立初始 `preprocessed_data_list` copy。
- `set_preprocessed_data_list()` 會清掉 datasets，並在資料已 epoch 時建立 `Epochs`。
- `clean_raw_data()` 會清 raw / preprocess / epoch / datasets。

### TrainingManager

`TrainingManager` 管訓練生命週期。

目前責任：

- model holder
- training option
- trainer
- saliency params
- training plan generation
- training start / stop
- export evaluation CSV
- trainer cleanup

重要行為：

- `generate_plan()` 需要 datasets、training option、model holder 都存在。
- `train()` 只負責叫現有 trainer 執行；沒有 trainer 會 raise。
- `set_training_option()` 和 `set_model_holder()` 目前不清 trainer，因為要保留 multi-experiment history。

## Controllers 現況

Controllers 不是純薄轉接。它們有一部分 UI 解耦責任，也有一部分 workflow / state transition 邏輯。

| Controller | 目前責任 |
| --- | --- |
| `DatasetController` | import files、去重、loader dispatch、label import、metadata、channel selection、observer notification。 |
| `PreprocessController` | 對 preprocessed data 做 copy、套用 processor、atomic swap 回 Study、發出 preprocess event。 |
| `TrainingController` | training readiness、plan generation trigger、start / stop、monitor thread、history formatting。 |
| `EvaluationController` | 讀取 training plans、匯總 evaluation result、model summary。 |
| `VisualizationController` | 讀取訓練結果與 saliency params、montage / channel data 查詢。 |

後端重構時不能假設 controller 只是 UI adapter。現在某些流程邏輯確實在 controller 裡，尤其是 import、preprocess copy/swap、training monitor。

## 主要資料流

### Import

```text
UI DatasetPanel
  -> DatasetController.import_files(...)
  -> RawDataLoaderFactory.load(path)
  -> RawDataLoader.apply(study)
  -> Study.set_loaded_data_list(...)
  -> DataManager.set_loaded_data_list(...)
```

assistant / headless path：

```text
LLM real tool
  -> get_application_service(study).execute(LoadDataCommand(...))
  -> DataCompatibilityCommandService
```

### Preprocess

```text
UI PreprocessPanel or agent real tool
  -> ApplicationService.execute(PreprocessCommand(...))
  -> PreprocessCommandService
  -> copy current study.preprocessed_data_list
  -> processor.data_preprocess(...)
  -> Study.set_preprocessed_data_list(...)
  -> DataManager.set_preprocessed_data_list(...)
```

這裡已經有避免 in-place 修改 UI 正在讀取資料的設計：controller 先 copy，再 atomic swap list reference。

### Dataset / Training

```text
ApplicationService.execute(SaveDatasetSplitCommand(...))
  -> DatasetGenerationCommandService
  -> validate preview receipt and epoch revision
  -> save typed split specification / fingerprint
  -> no dataset masks or training tensors materialized

ApplicationService.execute(TrainCommand(...))
  -> DatasetGenerationCommandService.prepare_saved_split_candidate()
  -> materialize masks and audit leakage / coverage without publishing partial state
  -> TrainingCommandService resource preflight
  -> commit verified split and start training
```

UI 透過 typed application actions 保存 split / model / training options；lower-level training
execution 仍可委派既有 controller / manager，但不以 controller state 建立第二份 product truth。

## Runtime Truth

目前比較可信的 runtime truth 來源：

- `Study` live state
- `DataManager` data lifecycle state
- `TrainingManager` training lifecycle state
- `ApplicationViewPublication.state.pipeline_stage` 與同 generation capability policy
- controller observer events（只作 refresh signal，不是獨立 workflow/state truth）
- quality dashboard / targeted tests

不應依賴：

- UI display text
- chat wording
- legacy docs
- 退役的 `AQ-*` / `Prep Gate` / `Repair Loop` task systems
- 舊絕對路徑

## 已驗證事實

- `Study.get_controller()` 會 cache built-in controllers；`tests/unit/test_architecture.py` 有 coverage。
- Product MainWindow 透過 narrow typed query/publication/action ports materialize 五個 panels；
  standalone/test constructors 仍有明確隔離的 controller compatibility signatures。
- `BackendFacade` module 已移除；product runtime packages 和 tests 不應使用它。
- `ApplicationService` 第一版已可回傳 state snapshot、capability policy 和
  `CommandResult`，並可執行 load / label / preprocess / epoch / dataset /
  training setup / train / reset commands。
- `DataInterpretationCommandService` / `DataInterpretationApplyService` 已由 focused unit tests
  覆蓋 scan / preview / validate / clear，以及 apply 後 reviewed metadata / label-import recipe
  state 同步。
- `AnalysisCommandService` 已由 focused unit tests 覆蓋 evaluation summary、visualization
  readiness、saliency normalization / configuration 和 confirmed montage apply。
- `Study` 已拆出 `DataManager` 和 `TrainingManager`，但還保留 backward-compatible delegation properties。
- pipeline stage 是從 live `Study` state 計算，不是文件或 UI label 推導。
- tiny Study training E2E smoke 已通過，證明 `Study -> TrainingManager` delegation 的代表性 train/evaluate path 目前可跑。

## 待審視問題

這些才是後端重構時應該看的問題：

1. `Study` 是否應繼續保留大量 delegation property，還是逐步收斂成更明確的 state API。
2. controller 裡的 workflow logic 是否要下沉到 service / manager，讓 controller 更接近 UI adapter。
3. 剩餘 standalone/test controller compatibility 何時能由 typed application ports 取代，而不讓
   product UI 或 assistant 回流成第二套 state truth。
4. 哪些 UI consumer 仍直接持有 live domain/runtime object，以及 ownership / stale-generation /
   teardown boundary 應如何收斂。
5. 哪些 observer refresh 仍未以 matching publication revision acknowledgement 驗證，避免把
   refresh coordinator 的存在誤寫成所有 panel 已統一。
6. error handling 已有第一版分類，但仍需用更多 real workflow 驗證是否足以支撐
   tool-call verification，包括可恢復狀態和可回報給 agent 的 diagnostics。

## 目標方向

這是目前確認的後端重構目標方向。

理想上，後端不應該讓 UI、assistant tools、scripts 各自繞不同流程。

目標方向是建立一層共用的 Application Service / Command API：

```text
PyQt UI panels
Assistant tools
Headless scripts
  |
  v
Application Service / Command API
  |
  v
Study / Domain State
  |
  +-- DataManager
  +-- TrainingManager
  +-- Evaluation / Visualization services
  |
  v
Infrastructure
  +-- MNE / file loaders
  +-- PyTorch models
  +-- filesystem
  +-- runtime diagnostics
```

這層 command API 應該承接軟體能力面，例如：

- `load_data(files)`
- `attach_labels(mapping)`
- `apply_preprocess(config)`
- `configure_dataset_split(config)`
- `configure_training(config)`
- `start_training()`
- `stop_training()`
- `get_current_state()`

理想狀態下，不管是人按 UI，還是 agent tool-call，最後都呼叫同一批 command。UI 和 agent 只負責不同的表達方式，不各自實作 workflow。

```text
UI Dataset button
  -> LoadDataCommand(files)

Agent tool: load_data(files)
  -> LoadDataCommand(files)
```

Assistant / script 的穩定入口是 `ApplicationService / Command API` 或薄 command adapter；
`BackendFacade` 已物理移除，也不是 compatibility target。

這個方向已由使用者確認。Current product path 已由 `ApplicationService` 組合 Study-owned focused
services / domain ports；Product MainWindow 與 assistant 都從 typed application boundary 進入。
Controller registry 仍存在於 outer/compatibility 邊界，後續只收斂有證據可替代的殘留，不可把它
重新寫成 product command 或 render truth。

## 重構原則

目前不應直接大改 `Study`，也不應重新加入 `BackendFacade`。

比較安全的順序是：

1. 盤點每個 controller 裡的 workflow logic。
2. 把真正 business workflow 抽成 service / command。
3. controller 變成 UI adapter，只負責輸入轉換、事件通知、呼叫 command。
4. agent tools 只包 command input / output，不自己實作另一套流程。
5. 先測 command API，再用 UI / agent integration tests 驗證兩條入口一致。

## 目前判斷

目前 backend 已建立 Application Service / Command API、focused command services，並物理移除
`BackendFacade` 與 product live-object result payload，但仍處在 UI/controller 邊界收斂的
中間狀態。Injected controllers、lower-level domain-object presentation、
publication acknowledgement 和 refresh adoption 都還有已知 debt。

因此下一階段後端重構不應直接大改資料流。比較合理的順序是：

1. 盤點剩餘 controller-owned workflow、lower-level domain-object presentation 和非
   publication refresh；不可把 domain object 重新放回 product result。
2. 以 focused slice 將 business workflow 下沉到 service / command，controller 保留必要
   adapter / observer 責任。
3. 讓 display refresh 以 generation-bound publication 和 acknowledgement 驗證；observer event
   只作 signal，不建立第二份 state truth。
4. 繼續將 legacy compatibility tests 改成 `CommandResult`、state publication 和 visible
   behavior assertions，再移除有證據可替代的 controller compatibility。
