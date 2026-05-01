# Backend Architecture

最後更新：`2026-05-02`

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
UI 執行動作仍大量直接吃 controllers，controller 邊界收斂與完整 runtime 證據仍未完成。

## 一句話架構

XBrainLab backend 目前是以 `Study` 作為中心狀態容器，`DataManager` 和
`TrainingManager` 分別承接資料生命週期與訓練生命週期；UI 仍主要透過
controller 操作 `Study`，但 UI-facing readiness 判斷已開始讀
`ApplicationService / Command API`；assistant / headless script 的 `BackendFacade`
已改成包 command layer。

## 實際分層

```text
PyQt panels
  |
  +--> UI action execution (legacy)
  |       |
  |       v
Study.get_controller(...)
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
  v
same cached controllers from Study

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

因此現在 UI 的主要執行入口仍是 controller layer，而不是 facade。

但第一批 UI-facing decision 已改讀 ApplicationService capability policy：

- Dataset import readiness 先讀 `load_data` capability，blocked reason 由 backend policy 產生。
- Preprocess sidebar 的 filtering / resample / rereference / normalize readiness 先讀
  `preprocess` capability。
- Epoching readiness 先讀 `create_epoch` capability。
- Training sidebar 的 Start Training enabled / tooltip / click-time guard 先讀 `train`
  capability，不再自己重寫一套 dataset/model/training option 判斷。
- Chat panel / AgentManager 的 compact backend diagnostics 讀 `BackendFacade.get_state()` 和
  `BackendFacade.get_capabilities()`。

UI 測試中的 mock `Study` 仍走 legacy fallback，避免 unit test 用不完整 mock state
誤觸真 ApplicationService policy。

### Assistant / headless 入口

`BackendFacade` 是 app 內 assistant real tools 和 headless scripts 的高階入口。

它會建立或接收一個 `Study`，再建立 `ApplicationService`。`BackendFacade`
保留舊方法名稱和舊回傳形狀，例如 `load_data()` 回傳 `(count, errors)`，
但核心 workflow 已開始委派給 command layer。

`ApplicationService` 會拿同一組 cached controllers：

- `dataset`
- `preprocess`
- `training`
- `evaluation`
- `visualization`

目前 `XBrainLab/llm/tools/real/dataset_real.py`、`preprocess_real.py`、`training_real.py` 都會透過 `BackendFacade(study)` 操作 backend。

結論：`BackendFacade` 可以視為 agent/tool surface 的相容入口，但它不再是新的
核心邏輯層。新邏輯應進 `ApplicationService` 或後續更細的 command handler；
UI 仍未改成 service-first。

### Agent command surface

Agent 現在不再只靠 `pipeline_state.py` 的 stage table 決定工具可用性。

新增 `XBrainLab/llm/tools/application_surface.py`，將 agent tool names 對映到
ApplicationService command names：

| Agent tool | Application command |
| --- | --- |
| `load_data` | `load_data` |
| `attach_labels` | `attach_labels` |
| `apply_standard_preprocess` / `apply_bandpass_filter` / `apply_notch_filter` / `resample_data` / `normalize_data` / `set_reference` / `select_channels` / `set_montage` | `preprocess` |
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

### Script / headless path

Headless script 仍應使用 `BackendFacade`。`BackendFacade` 保留舊 method names 和 return
shape，但核心 load / attach labels / preprocess / epoch / dataset / training / reset workflow
都透過 `ApplicationService.execute()`。不要在 script 裡直接重建 readiness 判斷；需要狀態或
blocked reason 時使用 `BackendFacade.get_state()` / `get_capabilities()`。

### Application Service / Command API

第一版位置：

- `XBrainLab/backend/application/commands.py`
- `XBrainLab/backend/application/state.py`
- `XBrainLab/backend/application/capabilities.py`
- `XBrainLab/backend/application/results.py`
- `XBrainLab/backend/application/errors.py`
- `XBrainLab/backend/application/service.py`

目前已提供：

- `ApplicationService.get_state()`：回傳可序列化 state snapshot，包含
  raw/preprocessed/epoch/dataset/training/evaluation/visualization、active dataset /
  training、`last_error` 和 diagnostics。
- `ApplicationService.get_capabilities()`：由 backend state 產生 capability policy，
  阻擋缺前置條件的 command，例如沒有 raw data 不能 preprocess、epoch/dataset 後不能
  一般性 `load_data`、沒有 dataset/model/training option 不能 train。
- `ApplicationService.execute(command)`：回傳 `CommandResult`，包含
  status、command name、message、changed state、error type、recoverable 和 diagnostics。
- 已接上的核心 commands：
  `load_data`、`attach_labels`、preprocess operations、`create_epoch`、
  `generate_dataset`、`configure_training`、`train`、`stop_training`、`reset_session`。
- contract 已保留但尚未實作的 future commands：
  `evaluate`、`visualize`、`saliency`、`new_session`。這些 command 有穩定 command
  object / policy entry，但 capability policy 會標成 unavailable，不應被 UI 或 agent
  當作可執行能力。

重要邊界：

- command 目前仍透過既有 controllers 執行，以保留 observer event 與 UI refresh 行為。
- `BackendFacade` 是 wrapper；它不應再承載新的 workflow business logic。
- `set_montage()` 仍保留在 `BackendFacade` 的 legacy path，因為它牽涉 UI confirmation
  和 channel mapping；`ApplicationService` 裡的 `set_montage` preprocess operation 會回
  confirmation-required failure，不再回假成功訊息。
- `reset_session` 目前代表清掉 active backend session：raw / preprocess / epoch /
  dataset / trainer / model option / saliency config 都會失效；有既有 state 時需要
  confirmation。

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
