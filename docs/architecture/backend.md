# Backend Architecture

最後更新：`2026-05-05`

## 可信度

狀態：`partially-verified`

這份文件已對照目前 source code：

- `XBrainLab/backend/application/*.py`
- `XBrainLab/backend/facade.py`
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
smart parse、remove files、label import、montage confirmation。controller 邊界尚未完整收斂，
但上述 real `Study` mutating paths 已回 `CommandResult`；mock/unit-test fallback 和部分
read-only panel refresh 仍保留相容 controller path。2026-05-03 backend hardening 又把
dataset generation 的 apply/audit failure 包成同一個 rollback boundary，避免 datasets /
generator / trainer 半成功殘留；`evaluate` 和 `clear_training_history` 也改成需要真的
training plan history，不能只因 trainer 物件存在就開啟。2026-05-04 Goal 1 第一個
backend slice 又新增 Data Interpretation command baseline，讓 scan / preview / validate /
apply / recipe reload 開始進入同一個 Application Service command spine。後續 Goal 1 slices
已把 Data Interpretation 暴露到 agent tools、Dataset panel 主要 import entry，並新增
`backend.application.automation` 作為 headless / MCP-ready JSON adapter；它只轉 command
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
`ApplicationService`。最新 dataset cleanup slice 又把 `generate_dataset`、`clear_datasets`、
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
mock / legacy adapter 回傳 `None` 的相容情境。
後續 Training sidebar cleanup 也把重新 split 前的 dataset cleanup 和 Clear History 接回
`ClearDatasetsCommand` / `ClearTrainingHistoryCommand`；successful service result 不再落回
training controller mutation。
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

## 一句話架構

XBrainLab backend 目前是以 `Study` 作為中心狀態容器，`DataManager` 和
`TrainingManager` 分別承接資料生命週期與訓練生命週期；UI 仍保留 controller 操作
`Study` 的歷史路徑，但高價值 workflow 按鈕已開始透過 `ApplicationService / Command API`
執行；assistant / headless script 的 `BackendFacade` 已改成包 command layer。

## 實際分層

```text
PyQt panels
  |
  +--> UI action execution
  |       |
  |       +--> ApplicationService.execute(...) for import / label / metadata / preprocess / epoch / split / query / train / reset / montage
  |       |
  |       v
  |     Study.get_controller(...) mock fallback / read-only UI population
  |
  v
DatasetController / PreprocessController / TrainingController
EvaluationController / VisualizationController
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
BackendFacade
  |
  v
ApplicationService / Command API
  |
  +--> DataInterpretationCommandService
  |       +--> scanner / candidate builder / review service / recipe state
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
  |       +--> split config / dataset generation / split audit / rollback / dataset cleanup
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
same cached controllers from Study

Headless / MCP-ready automation
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

`XBrainLab/ui/main_window.py` 在初始化 panels 時直接呼叫：

- `study.get_controller("dataset")`
- `study.get_controller("preprocess")`
- `study.get_controller("training")`
- `study.get_controller("evaluation")`
- `study.get_controller("visualization")`

因此現在 UI 仍會取得 controller layer；這些 controller 仍是 panel refresh、dialog-local
logic 和部分 legacy action 的現況入口。但高價值 workflow action 已不再只直接呼叫
controller，而是先經過 UI command adapter 進 `ApplicationService.execute()`。

第一批 UI-facing decision 已改讀 ApplicationService capability policy：

- Dataset import readiness 先讀 `load_data` capability，blocked reason 由 backend policy 產生。
- Preprocess sidebar 的 filtering / resample / rereference / normalize readiness 先讀
  `preprocess` capability。
- Epoching readiness 先讀 `create_epoch` capability。
- Training sidebar 的 Start Training enabled / tooltip / click-time guard 先讀 `train`
  capability，不再自己重寫一套 dataset/model/training option 判斷。
- Chat panel / AgentManager 的 compact backend diagnostics 讀 `BackendFacade.get_state()` 和
  `BackendFacade.get_capabilities()`。

同一批 high-value execution 也已接 service-backed command adapter：

- Dataset import 使用 `LoadDataCommand`。
- Dataset direct file import 的 successful `LoadDataCommand` path 不再再呼叫
  `DatasetController.import_files()`；controller import 只保留給 command adapter 不存在的
  mock / legacy `None` fallback。
- Dataset clear / reset 使用 `ResetSessionCommand(confirmed=True)`。
- Preprocess filtering / resample / rereference / normalize 使用 `PreprocessCommand`。
- Preprocess reset 使用 `ResetPreprocessCommand(confirmed=True)`；successful service result 不再
  落回 `PreprocessController.reset_preprocess()`。
- Channel selection 使用 `PreprocessCommand(SELECT_CHANNELS)`。
- Epoching 使用 `CreateEpochCommand`。
- Split / model / training setting dialog submit 使用 `GenerateDatasetCommand` /
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

UI 測試中的 mock `Study` 仍走 legacy fallback，避免 unit test 用不完整 mock state
誤觸真 ApplicationService policy。

仍保留 controller / UI-request path 包含：

- mock / unit-test compatibility fallback。
- montage picker 的 human-in-the-loop UI request；真正 apply 已走 `ApplyMontageCommand`。
- panel read-only refresh / population，例如 tables、plots、combo box contents。

### Assistant / headless 入口

`BackendFacade` 是 app 內 assistant real tools 和 headless scripts 的高階入口。

它會建立或接收一個 `Study`，再建立 `ApplicationService`。`BackendFacade`
保留舊方法名稱和舊回傳形狀，例如 `load_data()` 回傳 `(count, errors)`，
但核心 workflow 已開始委派給 command layer。

`XBrainLab.backend.application.automation` 是新的 headless / MCP-ready adapter。它輸出
`ApplicationService` command schema、MCP-shaped tool specs 和 live capability / autonomy
policy，並將 JSON payload 驗證後轉成 typed command 再呼叫 `ApplicationService.execute()`。
`XBrainLab.mcp.server` 是目前的 stdio MCP server baseline；它只處理 MCP lifecycle / tool
transport，實際 tool call 仍包這層 automation adapter，而不是繞過 command layer 或直接碰
controller internals。

`ApplicationService` 會拿同一組 cached controllers：

- `dataset`
- `preprocess`
- `training`
- `evaluation`
- `visualization`

目前 `XBrainLab/llm/tools/real/dataset_real.py`、`preprocess_real.py`、`training_real.py`
大多仍可透過 `BackendFacade(study)` 操作 backend。另有一批 mapped workflow tools
已由 `LLMController` 透過 `execute_application_tool_command(...)` 直接執行
ApplicationService command 並回傳 `ToolCommandResult.from_command_result(...)`。

結論：`BackendFacade` 可以視為 agent/tool surface 的相容入口，但它不再是新的
核心邏輯層。新邏輯應進 `ApplicationService` 下的 focused command service / handler；
UI 目前是 service-first migration 的中間狀態，尚未完整完成。

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

- `ScanResult`：掃描 file / folder / BIDS-like source / recipe，列出 EEG files、label
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
`blocks_downstream_until_confirmed` 等 autonomy 欄位。這些欄位目前先支撐 backend / agent
adapter contract；UI import wizard 和 agent tool taxonomy 尚未使用這套新命令作為主入口。

### Agent command surface

Agent 現在不再只靠 `pipeline_state.py` 的 stage table 決定工具可用性。

新增 `XBrainLab/llm/tools/application_surface.py`，將 agent tool names 對映到
ApplicationService command names：

| Agent tool | Application command |
| --- | --- |
| `load_data` | `load_data` |
| `attach_labels` | `attach_labels` |
| `apply_standard_preprocess` / `apply_bandpass_filter` / `apply_notch_filter` / `resample_data` / `normalize_data` / `set_reference` / `select_channels` | `preprocess` |
| `set_montage` | `apply_montage` capability + UI confirmation request |
| `epoch_data` | `create_epoch` |
| `generate_dataset` | `generate_dataset` |
| `set_model` / `configure_training` | `configure_training` |
| `start_training` | `train` |
| `clear_dataset` | `reset_session` |

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

2026-05-02 product delivery slice 之後，mapped agent workflow tools 會優先直接執行
ApplicationService command，包含 `load_data`、`attach_labels`、preprocess tools、`epoch_data`、
`generate_dataset`、`set_model`、`configure_training`、`start_training`、`clear_dataset`。
`load_data` 會先做 directory expansion 再進 `LoadDataCommand`。`set_montage` 和
`switch_panel` 仍是 UI request path；`set_montage` 的 capability 由 `apply_montage` policy
決定，confirmation 後的 apply 走 `ApplyMontageCommand`。`list_files` / `get_dataset_info`
仍是 read-only / inspection tools，但現在也會經 typed result normalization，避免 legacy
`"Error: ..."` 或 `[]` 被誤當成功 visible response。

### Script / headless path

Headless script 仍應使用 `BackendFacade`。`BackendFacade` 保留舊 method names 和 return
shape，但核心 load / attach labels / preprocess / epoch / dataset / training / reset workflow
都透過 `ApplicationService.execute()`。不要在 script 裡直接重建 readiness 判斷；需要狀態或
blocked reason 時使用 `BackendFacade.get_state()` / `get_capabilities()`。

### Application Service / Command API

第一版位置：

- `XBrainLab/backend/application/commands.py`
- `XBrainLab/backend/application/analysis_service.py`
- `XBrainLab/backend/application/state.py`
- `XBrainLab/backend/application/capabilities.py`
- `XBrainLab/backend/application/data_compatibility_service.py`
- `XBrainLab/backend/application/data_interpretation.py`
- `XBrainLab/backend/application/data_interpretation_apply.py`
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
- `ApplicationService.execute(command)`：回傳 `CommandResult`，包含
  status、command name、message、changed state、error type、recoverable 和 diagnostics。
- 已接上的核心 commands：
  `scan_source`、`preview_interpretation`、`validate_interpretation`、
  `apply_interpretation`、`save_interpretation_recipe`、`reload_interpretation_recipe`、
  `load_data`、`attach_labels`、`import_labels`、`update_metadata`、`apply_smart_parse`、
  `remove_files`、preprocess operations、`create_epoch`、`generate_dataset`、
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
  `get_state()` / `get_capabilities()` 入口，但不再直接承接 snapshot helper 細節。
- `configure_training`、`train`、`stop_training`、`clear_training_history` 和 reset-time
  training config clear 的 handler 實作位置現在是 `TrainingCommandService`。它 owns model
  holder 建立、optimizer / device / evaluation option resolve、training option snapshot 和
  training lifecycle notification；`ApplicationService` 只做 dispatch、policy gate 和 result
  envelope。
- UI Training sidebar 的 Clear History action 會透過 `ClearTrainingHistoryCommand` 進入
  `TrainingCommandService`；只有 mock / legacy `None` adapter 情境才回到 controller fallback。
- `generate_dataset`、`clear_datasets`、split config、split audit、rollback 和
  `DatasetStateSnapshot.split_summary` 的實作位置現在是 `DatasetGenerationCommandService`。
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
  `execute_application_command()` 回傳 `None` 的 mock / legacy adapter 情境才回到 controller
  fallback。
- Data Interpretation command handlers 實作位置現在是
  `DataInterpretationCommandService`。它 owns scan/candidate/preview/validation/applied/recipe
  in-memory lifecycle 和 recipe label import state 更新；reviewed metadata apply 與 reviewed
  label carrier apply 則在 `DataInterpretationApplyService`。`ApplicationService` 不再直接承接
  這些 workflow 細節。
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
- `generate_dataset` 的 split apply 和 audit 共用 rollback boundary；audit blocking issue
  或 apply 中途例外都不應留下新 datasets / dataset generator / trainer。
- error boundary 對 command result 已足夠支撐 UI 顯示 blocked reason；UI / agent 必須把它
  轉成 visible user feedback，而不是只記在 diagnostics。

重要邊界：

- command 目前仍透過既有 controllers 執行，以保留 observer event 與 UI refresh 行為。
- Data Interpretation 的 lifecycle truth 目前在 `DataInterpretationCommandService`；UI、agent、
  automation 和 MCP 仍必須透過 `ApplicationService.execute()` 進入，不可直接建立第二套
  interpretation state。
- Analysis / visualization readiness truth 目前在 `AnalysisCommandService`，但 capability
  exposure 仍由 `ApplicationService.get_capabilities()` 產生。
- `BackendFacade` 是 wrapper；它不應再承載新的 workflow business logic。
- `BackendFacade(study)` 會重用掛在同一個 `Study` 上的 `ApplicationService`。這是 Data
  Interpretation lifecycle 的必要邊界，否則 `scan_source` 產生的 scan state 會在下一個
  `preview_interpretation` tool call 因重新建立 service 而遺失。
- `application_surface.py` 是 agent tool-name 與 ApplicationService command-name 的 adapter；
  read-only / legacy tools 可以保留在 facade path，但 visible output 必須經 typed formatter，
  不可讓 facade/string result 直接進 transcript。
- `set_montage()` 仍保留在 `BackendFacade` 的 legacy path，因為它牽涉 UI confirmation
  和 channel mapping；agent tool 的 availability 已改讀 `apply_montage` capability，
  confirmation 後由 `ApplyMontageCommand` 實際寫入 channel positions。
- `reset_session` 目前代表清掉 active backend session：raw / preprocess / epoch /
  dataset / trainer / model option / saliency config 都會失效；有既有 state 時需要
  confirmation。
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
- 提供 `pipeline_stage` computed property，狀態由 `XBrainLab/llm/pipeline_state.py` 即時計算，不是手動儲存。

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
  -> BackendFacade.load_data(...)
  -> DatasetController.import_files(...)
```

### Preprocess

```text
UI PreprocessPanel or BackendFacade
  -> PreprocessController.apply_*
  -> copy current study.preprocessed_data_list
  -> processor.data_preprocess(...)
  -> Study.set_preprocessed_data_list(...)
  -> DataManager.set_preprocessed_data_list(...)
```

這裡已經有避免 in-place 修改 UI 正在讀取資料的設計：controller 先 copy，再 atomic swap list reference。

### Dataset / Training

```text
BackendFacade.generate_dataset(...)
  -> Study.get_datasets_generator(config)
  -> TrainingController.apply_data_splitting(generator)
  -> generator.apply(study)
  -> Study/DataManager datasets

TrainingController.start_training()
  -> Study.generate_plan(...)
  -> TrainingManager.generate_plan(...)
  -> Study.train(interact=True)
  -> TrainingManager.train(...)
```

UI 也會透過 `TrainingController` 設定 model / option / data splitting。

## Runtime Truth

目前比較可信的 runtime truth 來源：

- `Study` live state
- `DataManager` data lifecycle state
- `TrainingManager` training lifecycle state
- `Study.pipeline_stage` computed property
- controller observer events
- quality dashboard / targeted tests

不應依賴：

- UI display text
- chat wording
- legacy docs
- 舊 `AQ-*` queue
- 舊絕對路徑

## 已驗證事實

- `Study.get_controller()` 會 cache built-in controllers；`tests/unit/test_architecture.py` 有 coverage。
- UI panels 目前直接吃 controllers，不吃 `BackendFacade`。
- `BackendFacade` 的主要用途是 agent/headless high-level API，目前已改成包
  `ApplicationService`。
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
3. `BackendFacade` 已開始作為 command wrapper；仍需審視 agent tools 是否直接格式化
   `CommandResult`，避免長期只靠 facade 舊回傳值。
4. UI 是否應逐步改成和 assistant 共用同一組 backend capability command，而不是各自繞 controller / facade。
5. error handling 已有第一版分類，但仍需用更多 real workflow 驗證是否足以支撐
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
- `generate_dataset(config)`
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

`BackendFacade` 可以保留，但它不應該變成另一個承載大量邏輯的平行 backend。比較好的角色是 command API 的 wrapper，讓 assistant / script 有穩定入口，同時不讓 UI 和 agent 行為分裂。

這個方向已由使用者確認。第一版 service 已採取保守路線：command layer 先呼叫既有
controllers，保留 observer event、refresh、lock / running-state 行為；後續再逐步把
controller 內的 business workflow 下沉。

## 重構原則

目前不應直接大改 `Study` 或把所有東西塞進 `BackendFacade`。

比較安全的順序是：

1. 盤點每個 controller 裡的 workflow logic。
2. 把真正 business workflow 抽成 service / command。
3. controller 變成 UI adapter，只負責輸入轉換、事件通知、呼叫 command。
4. `BackendFacade` 變成 assistant / script 的 wrapper，只呼叫 command。這一步已先完成
   核心 workflow 的第一版。
5. agent tools 只包 command input / output，不自己實作另一套流程。
6. 先測 command API，再用 UI / agent integration tests 驗證兩條入口一致。

## 目前判斷

目前 backend 架構不是一團亂，但它處在「已從 monolithic Study 拆出 managers，且
剛建立 Application Service / Command API，尚未完成 UI/controller 邊界收斂」的中間狀態。

因此下一階段後端重構不應直接大改資料流。比較合理的順序是：

1. 擴充 command API 的 real workflow coverage，尤其是 facade/controller parity 與
   更完整的 training execution boundary。
2. 逐步讓 controllers 呼叫 service，再由 controllers 發出既有 observer events。
3. 將 agent real tools 從舊字串 wrapper 慢慢改成 `CommandResult` formatter。
4. UI panel 仍保持保守，等 command API 和 tests 更穩再開始移入口。
