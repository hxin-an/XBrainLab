# UI 目前架構

最後更新：`2026-05-14`

## 範圍

這份文件描述 XBrainLab 目前已從 source 確認的 PyQt UI 架構，重點是
`MainWindow`、五個主要 workflow panel、observer refresh、assistant 接線，以及
aggregate info 更新方式。

本文不把未驗證的理想分層寫成既有事實。現況上，UI 仍直接使用 backend
controllers 的中間狀態，還不是一個完整由 Application Service 包住的形狀。
但 user-facing readiness / blocked reason 已開始讀 ApplicationService capability policy；
多數 high-value action execution 也已經透過 service-backed command adapter。

## 快速結論

| 問題 | 目前答案 |
| --- | --- |
| UI 是否統一走 command？ | 高價值 action 和 readiness 已優先走 `ApplicationService / Command API`；panel constructor 和 observer bridge 還保留 injected controller adapters。 |
| UI refresh 是否統一？ | command-result、navigation、known observer event 都進 refresh coordinator；mock / legacy fallback 仍可做 local refresh。 |
| 產品路徑還能偷走 legacy mutation 嗎？ | 已被 architecture guard 大幅限制；product UI method 不能直接呼叫 legacy fallback helper，也不能用 controller echo 判定 service success。 |
| 是否 full zero-controller UI？ | 還不是。現況是 controller adapter quarantine，不是 controller 全退場。 |
| 讀者應看哪裡？ | 先看本頁的例外地圖，再看 [validation](../validation/README.md) 的 checkpoint 摘要；不要從長串歷史紀錄倒推現況。 |

閱讀順序建議：先用「剩餘 UI controller 例外地圖」判斷某個 controller hit 是否仍是
product runtime risk；再看「已接上的高價值 path」確認 action / readiness 是否已走
command truth。不要只用 `rg get_controller` 的數量判斷架構好壞。

## 剩餘 UI controller 例外地圖

| 類型 | 代表位置 | 目前判斷 | 不能宣稱 |
| --- | --- | --- | --- |
| Panel bootstrap / observer bridge | `legacy_controller_bootstrap.py`、`BasePanel`、`QtObserverBridge` | observer bridge adapter，支撐現有 backend `Observable` event 到 Qt slot。 | 不能宣稱 UI 已完全不依賴 controllers。 |
| Command fallback compatibility | sidebar / panel `_legacy_*` helpers、`run_legacy_controller_fallback()` | mock / legacy non-`Study` only；real `Study` product path 若 command helper 不可用應 blocked/error，而不是 silent fallback。 | 不能把 fallback test 當 product success。 |
| Human request orchestration | montage picker、label import target selection、dialog-local validation | UI request path；confirmed action 才送進 command，例如 montage apply、smart parse、label import。 | 不能把 dialog orchestration 誤寫成 backend source-of-truth。 |
| Readonly display fallback | Evaluation / Visualization / Preprocess / Dataset panel display helpers | real `Study` 已優先用 typed command/query gate；no-service mock context 才讀 controller lists/plans/trainers。 | 不能宣稱所有 lower-level integration tests 都已改成 query truth。 |
| Assistant UI wiring | `AgentManager` | status / montage channel defaults 走 state query；legacy montage apply/channel fallback 只給 mock / legacy context。 | 不能宣稱 local LLM 長時間桌面 session 已人工驗收。 |
| Aggregate info | `InfoPanelService` | product runtime 不自行訂閱 controller events，資料列表透過 `QueryStateCommand(data_lists)`。 | 這不代表其他 panel observer adapters 已全部消失。 |

### Source 對照表

這張表把常見 `rg` 命中翻成現況判讀。它的用途是避免把所有
`controller` 字樣都當成同一種問題，也避免把 quarantine 誤寫成 target 已完成。

| Source hit | 目前分類 | 為什麼目前可接受或仍有 gap | 下一個可移除方向 |
| --- | --- | --- | --- |
| `legacy_controller_bootstrap.get_legacy_workflow_controllers_for_panel_bootstrap(...)` | panel constructor adapter | `MainWindow.init_panels()` 仍要把五個 workflow controllers 傳給既有 panel constructor。這不是 action / readiness / refresh truth；Evaluation / Visualization training-event bridges 現在只接受 injected training controller，不再從 `controller.study` 回頭 lookup。 | panel constructor 改吃 view model、service adapter 或 observer subscription token 後，移除 bootstrap controller bundle。 |
| `application_capabilities.run_legacy_controller_fallback(...)` | mock / legacy gate | real `Study` 會丟 `LegacyControllerFallbackUnavailableError`，所以 product runtime 不會 silent fallback 到 controller mutation。 | 保留到 mock-heavy UI tests 和 standalone legacy contexts 改成 service-backed fixture。 |
| Dataset / Preprocess / Training `_legacy_*` helpers | compatibility helper | helper 名稱讓 fallback 和 product command path 可讀性分開；architecture guard 阻擋 product method 直接呼叫 fallback gate 或直接 controller mutation。 | 將剩餘 mock-heavy tests 改成 command/state evidence，再逐步刪 helper。 |
| Dataset / Preprocess / Evaluation / Visualization display getters | readonly render fallback | real `Study` 先走 `QueryStateCommand`、`EvaluateCommand`、`VisualizeCommand` 或 `SaliencyCommand`；controller getter 只在 command helper 回傳 `None` 的 mock / no-service context 使用。 | 把 lower-level UI/component tests 的資料來源改成 typed command result 或 view model。 |
| `refresh_coordinator.refresh_after_*()` 呼叫 `update_panel()` / `update_info_panel()` / `refresh_backend_status()` | refresh surface | 這些 call 是 UI repaint entry，不是 backend truth。post-command refresh 由 `CommandResult.changed_state` 決定範圍，known observer event 由 owner panel 進 coordinator。 | 讓 panel `update_panel()` 內部完全讀 query/view-model，不再需要 controller render fallback。 |
| `InfoPanelService` controller reads | aggregate mock fallback | real `Study` 資料列表透過 `QueryStateCommand(data_lists)`；controller reads 只在 mock / legacy context。 | 測試改注入 query result 後，可移除 direct controller fallback。 |
| `AgentManager` montage fallback / status reads | assistant UI adapter | product status 讀 `ApplicationService.get_state()` / capabilities；montage channels 讀 `QueryStateCommand(state)`，legacy montage apply 只給 mock / legacy context。 | assistant montage flow 改成完整 command-backed dialog service 後，移除 fallback channel/apply helper。 |
| `plot_figure_window.py`、`export_saliency_dialog.py` 的 `plan.get_plans()` | lower-level domain object presentation | 這是在已取得 trainer/plan 後讀 domain object，不是重新從 `Study` 或 controller 判斷 product readiness。 | 若 evaluation/visualization view model 穩定，可把圖表資料也收進 typed result。 |
| `product_language.py` 的 `has_datasets` / `has_model` / `has_training_option` | state snapshot language | 這些是 `ApplicationState` 欄位，不是 controller readiness method。 | 保持只吃 state snapshot，避免未來直接接回 controller。 |

目前判斷：UI refresh / readiness 的 product truth 已經靠 command result、capability policy 和
query state 收斂，但還不是 target 的 full zero-controller UI。剩下的主要差距是 panel
constructor 還需要 controller adapter、部分 display fallback 為了 mock / legacy tests 保留、
以及人工 Windows desktop acceptance 尚未補上。

## 主要位置

| 路徑 | 責任 |
| --- | --- |
| `XBrainLab/ui/main_window.py` | 主視窗、top navigation、五個 panel 建立、assistant dock 入口。 |
| `XBrainLab/ui/legacy_controller_bootstrap.py` | 目前 panel constructor 仍需要 controller adapter 時的 named legacy quarantine；product refresh / action truth 不在這裡。 |
| `XBrainLab/ui/panels/` | Dataset、Preprocess、Training、Evaluation、Visualization workflow UI。 |
| `XBrainLab/ui/core/base_panel.py` | panel 共同基底，保存 controller、main_window、observer bridges。 |
| `XBrainLab/ui/core/observer_bridge.py` | 將 backend `Observable` event 轉成 Qt signal。 |
| `XBrainLab/ui/components/agent_manager.py` | UI 與 assistant / LLM controller 的接線層。 |
| `XBrainLab/ui/components/info_panel_service.py` | aggregate info panel 的集中更新服務；product runtime 由 command/navigation/observer shared refresh 呼叫 `MainWindow.update_info_panel()` -> `notify_all()`，mock / legacy context 才可直接訂閱 `data_changed` / `preprocess_changed`。 |
| `XBrainLab/ui/chat/` | in-app assistant 的 chat UI。 |

## 啟動與主視窗

`MainWindow` 接收一個 `Study` instance，並把它保存為 `self.study`。

初始化流程主要在 `XBrainLab/ui/main_window.py`：

1. 建立 top bar，加入五個 navigation buttons：Dataset、Preprocess、Training、Evaluation、Visualization。
2. 建立 `InfoPanelService(self.study, observe_controller_events=False)`，讓後續 sidebar 中的 aggregate info panel 可以註冊更新。
3. 建立 `QStackedWidget`。
4. 呼叫 `init_panels()` 建立五個主要 panel；目前 controller adapter lookup 只透過 named legacy bootstrap helper。
5. 呼叫 `init_agent()` 建立 assistant dock 與相關 signal wiring。

`init_panels()` 透過 `XBrainLab.ui.legacy_controller_bootstrap.get_legacy_workflow_controllers_for_panel_bootstrap(...)`
取得目前 panel constructor 相容所需的 controllers：

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
coordinator 邊界。2026-05-12 follow-up 又讓 `execute_application_command()` 在
`ApplicationService.execute(...)` 執行期間暫停同一個 MainWindow 的 observer-driven refresh；
command handler 內同步發出的 controller observer event 不會先刷新 UI，成功或失敗後由
`CommandResult.changed_state` 進入 `refresh_after_command()`。最新 cleanup 又讓 known observer
events 使用 coordinator refresh scope：
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

目前 `XBrainLab/ui/legacy_controller_bootstrap.py` 是 product runtime 取得五個 workflow
controller adapters 的 named quarantine。它只支撐 panel constructor / observer bridge /
legacy adapter compatibility，不是 action、readiness 或 refresh truth。
部分 panel constructor 的舊 `parent.study.get_controller(...)` fallback 已改成
`get_legacy_controller_from_study()`，只在 mock / legacy non-`Study` context 回傳 controller；
real `Study` panel 若缺少 MainWindow 注入 controller，不再自行走回 controller tree。UI 仍不是
完整 Application Service-only 分層，因為 panels 仍以 injected controllers 作為 observer bridge /
legacy adapter，但直接 controller lookup 已被收進 explicit legacy helper，且 architecture guard
不再允許 `main_window.py` 作為 blanket exception。
2026-05-14 後，`EvaluationPanel` 和 `VisualizationPanel` 的 training observer bridge 也不再從
`controller.study.get_controller("training")` 取得 fallback controller；沒有 injected training
controller 的 standalone context 只是不建立 training lifecycle bridge。

## ApplicationService Readiness Gate

`XBrainLab/ui/application_capabilities.py` 是 UI 進入 command spine 的主要薄 adapter。
它負責從 nearest `main_window.study` 取得 `ApplicationService`，提供 capability lookup、
blocked reason copy、command execution、post-command refresh，以及 mock / legacy fallback
邊界。

### 已接上的高價值 path

| UI area | Backend truth | 現況 |
| --- | --- | --- |
| Data Import / recipe | `scan_source`、`preview_interpretation`、`validate_interpretation`、`apply_interpretation`、`reload_interpretation_recipe` | real `Study` 走 command sequence；direct file import fallback 只留給 no-service mock / legacy context。 |
| Dataset edit actions | `update_metadata`、`apply_smart_parse`、`remove_files`、`import_labels`、`reset_session` | confirmed mutation 走 command；table render 和 channel dialog 在 real `Study` 讀 `QueryStateCommand(data_lists)`。 |
| Preprocess / epoch | `preprocess`、`create_epoch` | filter / resample / rereference / normalize / epoch 走 command；epoch dialog 和 preview data 走 query-backed lists。 |
| Dataset generation / training config | `generate_dataset`、`clear_datasets`、`configure_training` | split replacement、model selection、training settings defaults 不再以 stale controller echo 判定 service success。 |
| Training | `train`、`stop_training` | enabled capability 直接 dispatch command；long-running training 先顯示 confirmation；controller running checks 只在 no-capability fallback。 |
| Evaluation / visualization / saliency | `evaluate`、`visualize`、`saliency` | typed readonly command 先決定 display gate；blocked/unavailable 會清空 stale controller display。 |
| Montage | `QueryStateCommand(state)`、`apply_montage` | dialog channel defaults 走 state query；confirmed positions 走 `ApplyMontageCommand`；picker/matching 仍是 UI request。 |
| Chat diagnostics | `get_state()`、`get_capabilities()` | assistant status 使用 backend state/capability snapshot，不把 missing capability 顯示成 debug error。 |

### Guarded boundary

- UI product methods 不可直接呼叫 `run_legacy_controller_fallback()`；fallback 必須收在
  `_legacy_*` helper 或明確 legacy adapter boundary。
- 有 backend capability 的 command path 不可用 `controller.is_training()`、`has_datasets()`、
  `get_trainer()`、`validate_ready()`、`has_model()`、`has_training_option()` 重新 gate real
  `Study` readiness。
- service success path 不可再讀 `TrainingController.get_model_holder()` 這類 controller echo
  重新判定 command success。
- `main_window.py` 不再是 direct `study.get_controller(...)` 例外；panel bootstrap lookup 只能待在
  `legacy_controller_bootstrap.py`。
- product-success integration tests 不可用 `BackendFacade`、legacy fallback helper、direct
  mutable `Study` state、positive `study.get_controller()` assertion、no-crash / generic string
  當成功證據。

這些 guard 是 **product runtime fallback boundary**，不是 full zero-controller UI 證明。

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
`refresh_after_observer()`，讓 aggregate info panel、assistant backend status 和 downstream
analysis panels 不必等下一個 command result 或 tab switch；`training_updated` 也保留 live
`update_loop()`，但現在會在 live progress 更新後進入 training-owner coordinator scope。
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
| `TrainingPanel` | `training_started`、`training_stopped`、`config_changed`、`training_updated`、`history_cleared`、dataset `data_changed`、preprocess events | start/stop/config/history handlers update training UI and shared status; `training_updated` uses live `update_loop()` and then enters the training-owner coordinator scope; simple refresh bridge handles dataset/preprocess events |
| `EvaluationPanel` | training `training_stopped`、`history_cleared`、`config_changed`、preprocess `preprocess_changed` | simple refresh bridge |
| `VisualizationPanel` | training `training_stopped`、`history_cleared`、`config_changed`、preprocess `preprocess_changed`、visualization `montage_changed`、`saliency_changed` | simple refresh bridge |

各 panel 的 `update_panel()` 目前混合兩種資料來源：real `Study` product path 優先讀
ApplicationService query / typed readonly command result；mock / legacy fallback path 才讀
controller getter，例如 lists、plans、trainers 或 history。這是目前 UI refresh truth 最重要的
判讀規則：**controller getter 可以存在於 compatibility path，但不能再成為 real product
success truth。**

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
- 需要 legacy montage apply fallback 時，透過 explicit mock / legacy helper 取得 preprocess
  controller；real `Study` 初始化不再直接 `study.get_controller("preprocess")`。
- 刷新 chat product status 時讀 backend state / capability snapshot；若 capability snapshot
  缺少某些 command，該 command 會被視為 unavailable，而不是讓 UI status 變成 debug error。
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
- `scripts/dev/capture_ui_baseline.py` 會產出 top-level `artifacts/ui/*.png` live captures
  並比對 `tests/baselines/ui/` approved baseline；top-level captures 是 local generated
  output，不再 tracked。這是 visual regression evidence，不等於人工一定滿意，仍需人工
  UI 審核。

目前仍未完成的 UI product evidence：

- Windows Desktop shortcut 人工 click-through 到 assistant 對話還沒完成。
- label import dialog planning、montage picker / matching、部分 read-only detail population
  仍有 controller / UI-request compatibility path；Dataset table 和 Preprocess plot/history render
  已接 `data_lists` query，post-load label target selection 已改用 table row object，實際 smart
  parse、label import 和 montage confirmation apply 已接 service adapter。
- Guarded UI product smokes / real-tools evidence 已不再以 direct mutable `Study` state read
  作為成功證據；其他 integration suites 的 fixture/setup 型 direct state access 還需要分批判讀，
  不能一概當作 product acceptance。
- reset / new session 的 destructive confirmation 還需要完整 product walkthrough。

## Aggregate Info 更新

Aggregate info panel 的集中更新由 `InfoPanelService` 負責。

`MainWindow` 在建立 panels 前先建立 `InfoPanelService(self.study, observe_controller_events=False)`。
各 sidebar 內的 `AggregateInfoPanel(self.main_window)` 會在 parent 有 `info_service` 時自動註冊。

Product runtime 不讓 `InfoPanelService` 自行訂閱 controller events。Aggregate info refresh 由
`refresh_coordinator` shared-status path 呼叫 `MainWindow.update_info_panel()`，再委派到
`InfoPanelService.notify_all()`。Real `Study` data-list query 也透過
`execute_application_command(..., refresh=False)` 進入 ApplicationService；UI code 不應直接
建立 service 或呼叫 legacy facade。Direct command execution 只保留在
`application_capabilities.py` 的共用 helper 內，helper 會處理 real-Study detection、
mock / legacy fallback boundary 和 refresh policy。

若以 mock / legacy non-`Study` context 單獨建立並允許 observer events，`InfoPanelService` 可透過
`get_legacy_controller_from_study()` 建立 compatibility observer bridge：

- dataset controller 的 `data_changed`
- preprocess controller 的 `preprocess_changed`

事件發生後，service 會透過
`QueryStateCommand(query="data_lists", include_objects=True)` 取得 loaded /
preprocessed data list，並呼叫已註冊 info panel 的 `update_info(...)`。real `Study`
query 失敗時會回空 summary 並記 log，不會 fallback 到 controller list reads；mock /
legacy non-`Study` context 才保留 controller-list compatibility fallback。listeners 使用
`weakref.WeakSet` 保存，以降低已刪除 widget 被長期持有的風險。

## 現況邊界

目前 UI 架構可以交接為：

- `MainWindow` 是 shell，負責 top navigation、stack、五個主要 panel、assistant 入口。
- `legacy_controller_bootstrap.py` 是 panel constructor controller adapter 的 named quarantine。
- panels 經由 `BasePanel` / `QtObserverBridge` 監聽 backend `Observable` events，但 action /
  readiness / product-success truth 應回到 command / query。
- `AgentManager` 是 assistant 與 UI 的接線層，不是 backend truth owner。
- `InfoPanelService` 集中處理 aggregate info 的跨 panel 更新；real `Study` data-list summary
  走 `QueryStateCommand(data_lists)`。

需要注意的是，這不是理想化的 Application Service 分層。UI 目前仍透過 MainWindow-injected
controllers 建立 observer bridge，且 mock / legacy adapter 仍可使用 explicit controller fallback。
`InfoPanelService` 在 real `Study` runtime 已不再建立 direct controller bridge，但這只是
aggregate-info lookup cleanup，並不代表 UI controller observer 已全部退出。因此後續
如果要整理 backend / service layer，需要先盤點哪些 controller method 已經被 UI 直接依賴，再
決定是否抽出更穩定的 UI-facing application API。
