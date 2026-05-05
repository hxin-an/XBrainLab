# UI Architecture

最後更新：`2026-05-06`

## 範圍

這份文件描述 XBrainLab 目前已從 source 確認的 PyQt UI 架構，重點是
`MainWindow`、五個主要 workflow panel、observer refresh、assistant 接線，以及
aggregate info 更新方式。

本文不把未驗證的理想分層寫成既有事實。現況上，UI 仍直接使用 backend
controllers 的中間狀態，還不是一個完整由 Application Service 包住的形狀。
但 user-facing readiness / blocked reason 已開始讀 ApplicationService capability policy；
多數 high-value action execution 也已經透過 service-backed command adapter。

## 主要位置

| 路徑 | 責任 |
| --- | --- |
| `XBrainLab/ui/main_window.py` | 主視窗、top navigation、五個 panel 建立、assistant dock 入口。 |
| `XBrainLab/ui/panels/` | Dataset、Preprocess、Training、Evaluation、Visualization workflow UI。 |
| `XBrainLab/ui/core/base_panel.py` | panel 共同基底，保存 controller、main_window、observer bridges。 |
| `XBrainLab/ui/core/observer_bridge.py` | 將 backend `Observable` event 轉成 Qt signal。 |
| `XBrainLab/ui/components/agent_manager.py` | UI 與 assistant / LLM controller 的接線層。 |
| `XBrainLab/ui/components/info_panel_service.py` | aggregate info panel 的集中更新服務；成功資料變更由 `data_changed` / `preprocess_changed` 驅動，command/navigation/observer shared refresh 由 `MainWindow.update_info_panel()` 委派到 `notify_all()`。 |
| `XBrainLab/ui/chat/` | in-app assistant 的 chat UI。 |

## 啟動與主視窗

`MainWindow` 接收一個 `Study` instance，並把它保存為 `self.study`。

初始化流程主要在 `XBrainLab/ui/main_window.py`：

1. 建立 top bar，加入五個 navigation buttons：Dataset、Preprocess、Training、Evaluation、Visualization。
2. 建立 `InfoPanelService(self.study)`，讓後續 sidebar 中的 aggregate info panel 可以註冊更新。
3. 建立 `QStackedWidget`。
4. 呼叫 `init_panels()` 建立五個主要 panel。
5. 呼叫 `init_agent()` 建立 assistant dock 與相關 signal wiring。

`init_panels()` 直接透過 `Study.get_controller(...)` 取得 controllers：

- `dataset`
- `preprocess`
- `training`
- `evaluation`
- `visualization`

接著建立並加入五個 panel，順序也就是 navigation index：

| index | panel | controller 傳入 |
| --- | --- | --- |
| 0 | `DatasetPanel` | `DatasetController` |
| 1 | `PreprocessPanel` | `PreprocessController` + `DatasetController` |
| 2 | `TrainingPanel` | `TrainingController` + `DatasetController` |
| 3 | `EvaluationPanel` | `EvaluationController` + `TrainingController` |
| 4 | `VisualizationPanel` | `VisualizationController` + `TrainingController` |

`switch_page(index)` 切換 `QStackedWidget` 後，會委派
`XBrainLab.ui.refresh_coordinator.refresh_after_navigation()` 依 navigation index 刷新目標
panel、aggregate info panel 和 assistant backend status。因此 tab-switch refresh 的 panel mapping
與 shared status refresh 不再散在 `MainWindow` 內。Navigation refresh 現在也有 same-main-window
re-entrancy guard，避免 nested tab-switch refresh 對同一個 main window 重複刷新；但 refresh
來源仍有兩種：使用者切換頁面，以及 backend event 經 observer bridge 觸發。
後續 observer cleanup 已把單純的 `event -> update_panel()` bridge 先收斂到
`BasePanel._create_refresh_bridge()`；該 helper 統一接到 `refresh_from_observer()`，再委派
`refresh_coordinator.refresh_after_observer()`。這保留 backend observer event 語意，但把 safe
no-arg panel refresh、aggregate info refresh 和 assistant backend status refresh 放進同一個
coordinator 邊界。最新 cleanup 又讓 known observer events 使用 coordinator refresh scope：
`data_changed` 只由 `DatasetPanel` owner bridge 觸發 Dataset / Preprocess / Training refresh，
`preprocess_changed` 只由 `PreprocessPanel` owner bridge 觸發 Preprocess / Training /
Visualization refresh，training lifecycle events 只由 `TrainingPanel` owner callbacks 觸發
Training / Evaluation / Visualization refresh，`montage_changed` / `saliency_changed` 只由
`VisualizationPanel` owner bridge 觸發 Visualization refresh；其他同事件 subscriber 不再重複
刷新同一組 panels。`MainWindow.update_info_panel()` 現在委派到 `InfoPanelService.notify_all()`，
所以 coordinator 的 shared info refresh 會更新所有已註冊 sidebar aggregate panels；只在沒有
`info_service` 的 injected / legacy context 下才 fallback 到 direct `info_panel.update_info()`。

## Controller 取得方式

`Study.get_controller()` 在 `XBrainLab/backend/study.py` 中實作 controller cache。
第一次要求某類 controller 時建立 instance，之後回傳 cached instance。

目前 `MainWindow` 與部分 panel constructor 都會直接呼叫
`parent.study.get_controller(...)` 作為 fallback。這表示 UI 並非只依賴一層穩定
Application Service API，而是直接拿 workflow controllers 讀寫狀態與觸發操作。

## ApplicationService Readiness Gate

2026-05-02 起，UI 不再把所有 readiness 判斷都散落在 panels 裡。新增
`XBrainLab/ui/application_capabilities.py`，讓 UI component 從 nearest
`main_window.study` 取得 `BackendFacade(study).get_capabilities()`，並提供
`execute_application_command(...)` 讓 real `Study` path 可以直接執行
`ApplicationService.execute()`。

已接上的高價值 decision：

| UI area | Capability source | execution status |
| --- | --- | --- |
| Dataset data interpretation | `scan_source` / `preview_interpretation` / `validate_interpretation` / `apply_interpretation` / `reload_interpretation_recipe` | Dataset sidebar exposes file, folder/BIDS root, and saved-recipe entry actions; each runs scan or recipe reload -> preview dialog -> validate -> confirm/apply via service; mock / unsupported fallback can still call legacy `LoadDataCommand` / `DatasetController.import_files()` for the file action only |
| Dataset reset / clear | `reset_session` | `ResetSessionCommand(confirmed=True)` via service; fallback clears controller state |
| Preprocess operations | `preprocess` | `PreprocessCommand` via service for filter / resample / rereference / normalize; fallback calls `PreprocessController.apply_*()` |
| Channel selection | `preprocess` | `PreprocessCommand(SELECT_CHANNELS)` via service; fallback calls channel-selection controller path |
| Epoching | `create_epoch` | `CreateEpochCommand` via service; fallback calls `PreprocessController.apply_epoching()` |
| Split / model / training dialogs | `generate_dataset` / `configure_training` | `GenerateDatasetCommand` / `ConfigureTrainingCommand` via service; fallback calls training controller |
| Evaluation / visualization / saliency query | `evaluate` / `visualize` / `saliency` | service-backed typed query diagnostics, then existing controller UI refresh |
| Start / Stop Training | `train` / `stop_training` | `TrainCommand` / `StopTrainingCommand` via service; Start Training asks for long-running confirmation when backend capability requires it; fallback calls training controller only for mock / legacy paths |
| Metadata / smart parse / remove files / label import | `update_metadata` / `apply_smart_parse` / `remove_files` / `import_labels` | service command adapter for real `Study`; fallback calls dataset controller path |
| Montage confirmation apply | `apply_montage` | confirmed positions use `ApplyMontageCommand`; AgentManager and Visualization sidebar share a montage-position normalizer before command execution; montage picker / matching remains UI request path |
| Chat diagnostics | `get_state()` / `get_capabilities()` | `AgentManager` status wiring |

這代表 UI 現在顯示 enabled / disabled / tooltip reason 時，優先使用 backend-owned
policy；real `Study` action path 也優先走 command adapter。如果 unit test 或 legacy caller
傳入的是 mock / incomplete `Study`，helper 會回 `None` 並讓既有 controller fallback 繼續運作。

Training sidebar 已開始把這個 fallback boundary 顯式化：`run_legacy_controller_fallback()` 只允許
mock / legacy non-`Study` context 執行 controller fallback；real `Study` context 如果 command
helper 意外回 `None`，會拒絕 fallback，避免 product runtime silent controller mutation。目前已覆蓋
split cleanup / generate dataset、model selection、training settings、start / stop training 和
clear history。Preprocess sidebar 也已用同一 helper 覆蓋 filter / resample / rereference /
normalize / epoch / reset fallback。Dataset data-table/action paths 也已用同一 helper 覆蓋
metadata edit / batch metadata、smart parse、remove files、direct file import、clear dataset、
channel selection 和 post-load label compatibility fallback。Visualization saliency settings 和
Visualization sidebar / AgentManager montage confirmation fallback 也已用同一 helper 覆蓋。剩餘 `result is None` branches
主要是 service-unavailable UI error / blocked return，而不是 controller mutation fallback。
Dataset file import keeps `LoadDataCommand` / `DatasetController.import_files()` only as a
mock / legacy fallback when no ApplicationService command surface is visible. If the real
`scan_source` capability exists, a Data Interpretation command-sequence unavailable result is shown
as an interpretation error and does not fall back to direct load.
Training model selection also avoids a controller-truth echo on the service-success path:
after `ConfigureTrainingCommand` succeeds, the user-facing success message is based on the
command result and selected model holder instead of re-reading `TrainingController.get_model_holder()`.
The legacy fallback branch still verifies through the controller because that branch is explicitly
for mock / non-`Study` compatibility.
Training split replacement now also uses backend capability truth: when `generate_dataset` is
blocked only by existing generated datasets / trainer and `clear_datasets` is enabled, the UI asks
for confirmation and dispatches `ClearDatasetsCommand` before `GenerateDatasetCommand`, independent
of stale controller `has_datasets()` / `get_trainer()` state.
Start Training also follows backend capability truth: when the `train` capability is enabled, the
UI dispatches `TrainCommand` even if `TrainingController.is_training()` is stale. Controller
running checks remain only for no-capability mock / legacy paths.
Preprocess epoching follows the `create_epoch` capability directly: when `create_epoch` is enabled,
`open_epoching()` no longer re-checks the separate `preprocess` capability through `check_lock()` /
`check_data_loaded()`, so a valid epoching path is not blocked by a preprocess-only reason.
`tests/architecture_compliance.py` 會靜態檢查這條 boundary，防止新的 `result is None` branch
直接呼叫 controller mutation，也防止 service-backed success path 在
`execute_application_command()` 後回讀 `TrainingController.get_model_holder()` 這類 controller
echo 重新判定 command success。最新 guard 也防止有 `get_command_capability()` 的 UI command
path 用 `controller.is_training()`、`has_datasets()` 或 `get_trainer()` 做 pre-command
readiness gating，除非該 read 明確落在 `capability is None` legacy branch；guard extension
也覆蓋 Training readiness 的 `validate_ready()`、`has_model()`、`has_training_option()` echo。
`TrainingSidebar.check_ready_to_train()` 已改成明確 service-capability branch / no-capability
legacy branch，避免 stale controller readiness 混入 real `Study` capability truth。
Dataset sidebar render state follows the same boundary: with backend capabilities present,
`update_sidebar()` no longer reads `DatasetController.is_locked()` / `has_data()` before setting
button state or tooltips. Those controller reads are limited to explicit no-capability legacy
branches, and architecture compliance guards this pattern.
Evaluation panel now also uses the readonly `EvaluateCommand` result as a display gate. If a real
`Study` ApplicationService query reports evaluation blocked or unavailable, the panel clears to
`No Data Available` instead of reading stale injected `EvaluationController.get_plans()` data.
Visualization panel follows the same display-gate pattern for readonly `VisualizeCommand`: blocked
or unavailable visualization state clears plan/run controls and shows a user-facing readiness
message before any stale injected `VisualizationController.get_trainers()` data can render.
後續 raw-loader boundary cleanup 又把舊 `DatasetPanel.apply_loader()` 改成 explicit
mock / legacy adapter：real `Study` context 會拒絕 direct `loader.apply(study)`，並提示使用
Data Interpretation workflow。`find_study()` 現在也會透過 `controller.study` 辨識 real
`Study`，避免 panel 以 real controller 但沒有 main-window parent 時錯誤開放 fallback。
Architecture compliance 另新增 direct loader apply guard；非 legacy adapter 的 UI code 不可再
直接呼叫 `loader.apply(...study...)`。

第一個 manual refresh cleanup 已落在 Training sidebar：generate dataset、configure model /
training settings、start training 和 clear history 的 service-backed success path 不再直接呼叫
`check_ready_to_train()`；real `Study` readiness refresh 由 `refresh_after_command()` 依
`CommandResult.changed_state` 觸發。legacy mock / non-`Study` fallback 仍會手動刷新。
Dataset action handler 也已套用同一模式：smart parse、batch metadata 和 remove files 的
service-backed success path 不再直接呼叫 `panel.update_panel()`；legacy fallback 仍手動刷新。
Post-command refresh guard 現在也區分 missing-result compatibility 和 command failure：
`result is None` branch 不可直接 local refresh，必須走 explicit legacy-result helper；
`result.failed` branch 可保留 local restore / warning refresh。
Preprocess sidebar 保留的 mock / legacy epoch-reset shared-status helper 也改走
`refresh_shared_status()`，讓 compatibility path 的 aggregate info 和 assistant backend status
與 coordinator shared-status 邊界一致。
後續 downstream refresh cleanup 又把 analysis readiness scope 補進 coordinator：
`training_changed` 會刷新 Evaluation / Visualization panel，`epoch_changed` 會刷新 Visualization
panel，`evaluation_changed` 也會刷新 Visualization panel。這讓 training / epoch / evaluation
state 變化後的 analysis readiness 更依賴 `CommandResult.changed_state`，而不是只靠 controller
observer event 補刷新。

仍未完成：

- label import dialog planning、montage picker / matching、panel read-only population 還保留
  controller / UI-request compatibility path；實際 label import、smart parse、montage
  confirmation apply 已接 service command adapter。
- Dialog submit 後的參數 validation 還有許多 controller-local error handling。
- reset / new session command 已存在；destructive confirmation 的 product walkthrough 還沒完成。
- Start Training button path now mirrors the backend long-running autonomy boundary with a
  user-facing confirmation dialog before `TrainCommand`; automated evidence is in
  `artifacts/ui/training-start-confirmation/`.
- Dataset source-entry sidebar now exposes separate user-facing actions for EEG file(s),
  folder / BIDS root, and saved import recipe. Folder/BIDS and recipe paths do not use legacy
  controller fallback; automated sidebar evidence is in
  `artifacts/ui/data-source-entry-options/`. Recipe reload uses the
  `reload_interpretation_recipe` capability gate, rather than inheriting the scan-source gate.

## Panel 基底與事件更新

主要 panel 繼承 `BasePanel`。`BasePanel` 做三件事：

- 保存 `self.controller`
- 從 parent 推導 `self.main_window`
- 保存 `_bridges`，讓 `QtObserverBridge` 在 panel 生命週期內不被釋放，並在
  `cleanup()` 時解除訂閱

`BasePanel` 不會在 base constructor 自動呼叫 `init_ui()` 或 `_setup_bridges()`。
各 panel 會先完成自己的 helper/component 初始化，再明確呼叫 `_setup_bridges()` 與
`init_ui()`。

單純的 observer-driven panel refresh 應使用 `BasePanel._create_refresh_bridge()`，不要直接把
event handler 接到 `update_panel()`。需要特殊語意的 event，例如 import-finished handler、
TrainingPanel 的 start/stop/config/history handler 或 live training update loop，仍可接自己的
handler。TrainingPanel 的 high-level callbacks 會在完成 event-specific UI 更新後呼叫
`refresh_shared_status()`，讓 aggregate info panel 和 assistant backend status 不必等下一個
command result 或 tab switch；`training_updated` 因為是 high-frequency live update，仍只做
training UI 自身更新。
`refresh_after_observer()` currently treats `data_changed`, `preprocess_changed`, high-level
training lifecycle events, and visualization `montage_changed` / `saliency_changed` as known
state-changing events and maps them through the same panel-scope rules used by command-result
refresh. Unknown observer events still fall back to refreshing the source panel plus shared status.
`tests/architecture_compliance.py` 會阻擋新的 direct `_create_bridge(..., self.update_panel)`
和 direct `_create_bridge(..., self.refresh_from_observer)` call site；`BasePanel` helper 內部的
delegation 是唯一例外。

`QtObserverBridge` 的角色是把 backend 的 Python observer event 轉為 Qt signal：

- constructor 對 `Observable.subscribe(event_name, self._on_event)` 訂閱。
- backend event 發生時，`_on_event()` emit `triggered(args, kwargs)`。
- `connect_to(slot)` 包一層 wrapper，把 event args/kwargs 還原後呼叫 UI slot。
- `cleanup()` 會 unsubscribe 並 disconnect signal。

這個 bridge 讓 backend event 可以安全地推動 UI slot，不需要 panel 直接把 Qt
signal 寫進 backend controller。

## 主要 Panel Wiring

已從 source 確認的主要 event wiring：

| panel | 主要監聽事件 | refresh / handler |
| --- | --- | --- |
| `DatasetPanel` | `data_changed`、`import_finished` | simple refresh bridge owns success refresh; `DatasetActionHandler.on_import_finished()` only surfaces import warnings |
| `PreprocessPanel` | `preprocess_changed`、dataset `data_changed` | simple refresh bridge |
| `TrainingPanel` | `training_started`、`training_stopped`、`config_changed`、`training_updated`、`history_cleared`、dataset `data_changed`、preprocess events | start/stop/config/history handlers update training UI and shared status, `training_updated` uses live `update_loop()`, simple refresh bridge handles dataset/preprocess events |
| `EvaluationPanel` | training `training_stopped`、`history_cleared`、`config_changed`、preprocess `preprocess_changed` | simple refresh bridge |
| `VisualizationPanel` | training `training_stopped`、`history_cleared`、`config_changed`、preprocess `preprocess_changed`、visualization `montage_changed`、`saliency_changed` | simple refresh bridge |

各 panel 的 `update_panel()` 通常會直接呼叫 controller 的 getter，例如
`get_loaded_data_list()`、`get_preprocessed_data_list()`、`get_formatted_history()`、
`get_plans()`、`get_trainers()`，再更新 table、sidebar、plot、combo box 或 tabs。

## Assistant 接線層

Assistant 不是直接塞在 `MainWindow` 內部，而是由 `AgentManager` 管理。
`MainWindow.init_agent()` 建立 `AgentManager(self, self.study)`，再呼叫
`agent_manager.init_ui()`。

`AgentManager` 目前負責：

- 建立 `ChatController()` 作為 chat UI-side state。
- lazy 建立 `LLMController(self.study)`。
- 建立 `ChatPanel` 與 `QDockWidget`。
- 串接 chat panel signals：送出訊息、停止生成、切換 model、切換 execution mode、新對話。
- 串接 LLM controller signals：response、status、error、human interaction、streaming chunk、processing finished 等。
- 處理 assistant 要求的 UI interaction，例如切換 panel、開 montage picker、危險操作 confirmation。
- 用 `study.get_controller("preprocess")` 取得 preprocess controller，供 montage 套用等流程使用。
- 第一次打開 chat dock 或第一次啟用 local runtime 時，會先顯示 first-run consent；
  使用者知道 GPU/CPU resource、download estimate、cache status 後，才能 Enable /
  Download / Use existing cache / Later / Disable。若 runtime unavailable，dock 仍保持可見並在
  chat history / status summary 顯示原因。

換句話說，`AgentManager` 是 UI 和 assistant runtime 之間的 adapter / wiring layer；
它不是 backend 狀態的 source-of-truth。

### 2026-05-02 Chat Product Correction

人工驗收發現 ChatPanel 不能只算「有 dock、有 signal、有 baseline」：

- 使用者輸入 `hello` 曾出現 no-response，代表 normal chat path 沒有產品級 gate。
- 舊 ChatPanel 視覺仍像 debug dock：status 被塞在底部小字，空狀態缺乏下一步指引，
  bubble 和 composer 不足以讓第一次使用者理解 assistant 能做什麼。
- UI baseline 沒抓到這件事，因為 baseline 只比對像素和尺寸，不驗證互動是否有回覆。

本輪收斂後，ChatPanel 的 product contract 是：

- chat panel 內不再顯示 `Conversation` 標題、第二條 status footer、developer mode /
  step behavior controls 或第二個 options menu。對話區第一視覺是 empty state / transcript。
- 第一層 controls 收斂到 dock title bar：`XBrainLab`、retry icon、new conversation、
  settings menu、float/dock。`Clear conversation` 收進 settings menu；workflow / runtime
  details 放在 main status bar、tooltip、settings 或非 transcript diagnostics。
- 第一層 UI 不顯示 raw command names，例如 `load_data`、`configure_training`、
  `reset_session`；主介面顯示 `Load EEG data`、`Train model` 這類使用者語言。raw command
  diagnostics 只放在 tooltip / advanced details。
- `Coder / Local / Multi`、`Assistant mode`、`Step behavior`、`Step by step`、
  `Continue safely` 這類尚未成為正式產品 workflow 的開發者語言，不得出現在第一層 UI。
- empty state 必須可見，並說明 assistant 能做 state inspection、blocked reason explanation、
  load -> preprocess -> epoch -> dataset -> train guidance。
- conversation area 不能是一大片黑畫面；user / assistant bubble 必須有 padding、max width、
  readable contrast、right margin 和 word wrap，不能吃掉 user bubble 最後一個字。
- composer 必須清楚，有 `Send` / `Stop` state，processing 時禁用會造成 race 的 controls。
- `Retry` 沒有上一則 request 時必須 disabled；程式直接呼叫時也只顯示 notice/status，
  不可新增正式 assistant bubble。
- user bubble 在 380-460px dock 寬度下必須保留可讀最小文字欄，不能把 `hello` 切成難看的
  單字斷裂。
- normal message、empty response、worker error、local unavailable 都必須在 transcript 中形成
  可見結果，不能只更新 status label。
- `tests/integration/ui/test_product_walkthrough.py` 已新增 assistant click-through layout
  regression，覆蓋 header / status / controls 不重疊、command diagnostics 不污染主 UI、
  user bubble 不截字、composer / Send button fit，以及五個 panel navigation 基本控制。
- `scripts/dev/capture_ui_baseline.py` 已產出新的
  `artifacts/ui/ai-assistant-open.png`，並同步更新 approved baseline
  `tests/baselines/ui/ai-assistant-open.png`；這是 visual regression evidence，不等於人工
  一定滿意，仍需人工 UI 審核。

目前仍未完成的 UI product evidence：

- Windows Desktop shortcut 人工 click-through 到 assistant 對話還沒完成。
- label import dialog planning、montage picker / matching、read-only table / plot population
  仍有 controller / UI-request compatibility path；實際 smart parse、label import 和
  montage confirmation apply 已接 service adapter。
- reset / new session 的 destructive confirmation 還需要完整 product walkthrough。

## Aggregate Info 更新

Aggregate info panel 的集中更新由 `InfoPanelService` 負責。

`MainWindow` 在建立 panels 前先建立 `InfoPanelService(self.study)`。各 sidebar 內的
`AggregateInfoPanel(self.main_window)` 會在 parent 有 `info_service` 時自動註冊。

`InfoPanelService` 目前監聽：

- dataset controller 的 `data_changed`
- dataset controller 的 `import_finished`
- preprocess controller 的 `preprocess_changed`

事件發生後，service 會重新從 dataset/preprocess controllers 取得 loaded /
preprocessed data list，並呼叫已註冊 info panel 的 `update_info(...)`。listeners
使用 `weakref.WeakSet` 保存，以降低已刪除 widget 被長期持有的風險。

## 現況邊界

目前 UI 架構可以交接為：

- `Study` 是 UI 取得 workflow controllers 的入口。
- `MainWindow` 是 shell，負責 top navigation、stack、五個主要 panel、assistant 入口。
- panels 經由 `BasePanel` / `QtObserverBridge` 監聽 backend `Observable` events。
- `AgentManager` 是 assistant 與 UI 的接線層。
- `InfoPanelService` 集中處理 aggregate info 的跨 panel 更新。

需要注意的是，這不是理想化的 Application Service 分層。UI 目前會直接拿 controllers
讀取 workflow 中間狀態、呼叫 controller methods，部分 panel constructor 也保留
從 `parent.study.get_controller(...)` fallback 取 controller 的路徑。因此後續如果要整理
backend / service layer，需要先盤點哪些 controller method 已經被 UI 直接依賴，再決定是否
抽出更穩定的 UI-facing application API。
