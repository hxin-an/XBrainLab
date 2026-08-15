# UI 目前架構

最後更新：`2026-08-13`

## 範圍

這份文件描述 XBrainLab 目前已從 source 確認的 PyQt UI 架構，重點是
`MainWindow`、五個主要 workflow panel、observer refresh、assistant 接線，以及
aggregate info 更新方式。

本文不把未驗證的理想分層寫成既有事實。現況上，五個 product panels 都由
ApplicationService-backed typed ports 建立；Training 的 live progress 由 narrow transient port
傳遞，不再由 MainWindow 注入 controller bundle。Controllers 仍存在於 standalone/test
compatibility constructors，不能把這些殘留誤寫成 repo-wide zero-controller。

## 快速結論

| 問題 | 目前答案 |
| --- | --- |
| UI 是否統一走 command？ | Product action、readiness 與 state render 走 `ApplicationService / Command API` 和 typed ports；Training progress tick 走獨立 transient port。 |
| UI refresh 是否統一？ | Product state-changing repaint 只認 revisioned `ApplicationViewPublication`；navigation refresh 和 Training transient progress 分開，mock / compatibility context 才保留 observer/local refresh。 |
| 長工作進度與取消從哪裡來？ | UI 先向 application runtime 配置 operation ID，再由 `OwnedOperationPresenter` 把 backend snapshot 的 stage / determinate-or-indeterminate progress / phase 投影到 owning control 與 status bar；Cancel 不等待 shared command lock。 |
| 產品路徑還能偷走 legacy mutation 嗎？ | 已被 architecture guard 大幅限制；product UI method 不能直接呼叫 controller compatibility helper，也不能用 controller echo 判定 service success。 |
| 是否 full zero-controller UI？ | Product MainWindow wiring 已不使用 controller bundle；但 standalone/test compatibility constructors 與 outer controller adapters 尚未物理移除。 |
| 讀者應看哪裡？ | 先看本頁的例外地圖，再看 [validation](../validation/README.md) 的 checkpoint 摘要；不要從長串歷史紀錄倒推現況。 |

Preprocess plot lifecycle 是明確的 native-widget 例外：一般取消 close 只暫停並恢復 callbacks；
真正接受 application close 或 panel destruction 時，會關閉 PyQtGraph roots，避免 Qt 已刪除
axis text 後仍收到 resize callback 而 native abort。

閱讀順序建議：先用「剩餘 UI controller 例外地圖」判斷某個 controller hit 是否仍是
product runtime risk；再看「已接上的高價值 path」確認 action / readiness 是否已走
command truth。不要只用 `rg get_controller` 的數量判斷架構好壞。

## 剩餘 UI controller 例外地圖

| 類型 | 代表位置 | 目前判斷 | 不能宣稱 |
| --- | --- | --- | --- |
| Standalone Training compatibility | `TrainingPanel` / sidebar compatibility constructor parameters | Typed-port product mode 會丟棄 compatibility controllers；standalone/mock tests 仍可明確注入。 | 不能宣稱 repo 已物理移除所有 controller compatibility code。 |
| Command fallback compatibility | sidebar / panel `_compatibility_*` helpers、`run_controller_compatibility_call()` | mock / compatibility non-`Study` only；real `Study` product path 若 command helper 不可用應 blocked/error，而不是 silent fallback。 | 不能把 fallback test 當 product success。 |
| Human request orchestration | montage picker、label import target selection、dialog-local validation | UI request path；confirmed action 才送進 command，例如 montage apply、smart parse、label import。 | 不能把 dialog orchestration 誤寫成 backend source-of-truth。 |
| Readonly display fallback | Preprocess / Dataset panel display helpers | real `Study` 已優先用 typed command/query gate；no-service mock context 才讀 controller lists。Evaluation catalog、metrics 與 chart render 已完全改讀 ApplicationService 的 generation-bound detached publication；Visualization saliency render 也讀 immutable publication，不再保留 live Trainer/Plan/EvalRecord/Dataset UI path。 | 不能宣稱其他 lower-level integration tests 都已改成 query truth。 |
| Assistant UI wiring | `AgentManager` | status / montage channel defaults 走 state query；compatibility montage apply/channel fallback 只給 mock / compatibility context。 | 不能宣稱 local LLM 長時間桌面 session 已人工驗收。 |
| Aggregate info | `InfoPanelService` | product runtime 不自行訂閱 controller events，資料列表透過 `QueryStateCommand(data_lists)`。 | 這不代表其他 panel observer adapters 已全部消失。 |

### Source 對照表

這張表把常見 `rg` 命中翻成現況判讀。它的用途是避免把所有
`controller` 字樣都當成同一種問題，也避免把 quarantine 誤寫成 target 已完成。

| Source hit | 目前分類 | 為什麼目前可接受或仍有 gap | 下一個可移除方向 |
| --- | --- | --- | --- |
| Training typed-port constructor | Product port boundary | `MainWindow` 注入 query、publication、action、transient-progress ports；typed-port mode 丟棄 compatibility controllers。 | 將 standalone/mock tests 改成 typed fixtures 後再縮窄 compatibility signature。 |
| `application_capabilities.run_controller_compatibility_call(...)` | mock / compatibility gate | real `Study` 會丟 `ControllerCompatibilityUnavailableError`，所以 product runtime 不會 silent fallback 到 controller mutation。 | 保留到 mock-heavy UI tests 和 standalone legacy contexts 改成 service-backed fixture。 |
| Dataset / Preprocess / Training `_compatibility_*` helpers | compatibility helper | helper 名稱讓 fallback 和 product command path 可讀性分開；architecture guard 阻擋 product method 直接呼叫 fallback gate 或直接 controller mutation。 | 將剩餘 mock-heavy tests 改成 command/state evidence，再逐步刪 helper。 |
| Dataset / Preprocess / Visualization display getters | readonly render fallback | real `Study` 先走 `QueryStateCommand`、`VisualizeCommand` 或 `SaliencyCommand`；controller getter 只在 command helper 回傳 `None` 的 mock / no-service context 使用。Evaluation 不在這個 fallback 類別：catalog 走 `EvaluateCommand`，chart data 走 generation-bound `EvaluationRenderPublication`，沒有 controller display fallback。 | 把其餘 lower-level UI/component tests 的資料來源改成 typed command result 或 view model。 |
| `ApplicationViewPublication` panel subscriptions；`refresh_coordinator.refresh_after_*()` | refresh surface | Product state-changing repaint 由 monotonic application revision 觸發；`refresh_coordinator` 只保留 navigation、transient progress 和 non-`Study` compatibility routing，不得從 product `CommandResult.changed_state` 建立第二套 state truth。 | 讓每個 product panel 只提交成功 render 的 revision，並逐步移除 controller render fallback。 |
| `InfoPanelService` controller reads | aggregate mock fallback | real `Study` 資料列表透過 `QueryStateCommand(data_lists)`；controller reads 只在 mock / compatibility context。 | 測試改注入 query result 後，可移除 direct controller fallback。 |
| `AgentManager` montage fallback / status reads | assistant UI adapter | product status 讀 `ApplicationService.get_state()` / capabilities；montage channels 讀 `QueryStateCommand(state)`，legacy montage apply 只給 mock / compatibility context。 | assistant montage flow 改成完整 command-backed dialog service 後，移除 fallback channel/apply helper。 |
| `plot_figure_window.py` 的 plan / record reads | lower-level domain object presentation | 這是在通用 figure window 已取得 domain object 後讀圖表資料；Visualization 的隱藏 export dialog 與未引用 Model Summary dialog 已移除。 | 通用 figure window 後續可再改吃 typed plot publication；不可把 live object path接回 Visualization UI。 |
| `product_language.py` 的 `has_datasets` / `has_model` / `has_training_option` | state snapshot language | 這些是 `ApplicationState` 欄位，不是 controller readiness method。 | 保持只吃 state snapshot，避免未來直接接回 controller。 |

目前判斷：UI refresh / readiness 的 product truth 已經靠 application publication、capability
policy 和 query state 收斂；五個 product panel constructors 也已使用 typed ports。剩下的主要
差距是 mock / no-runtime compatibility signatures、refresh exact-commit evidence，以及人工
Windows desktop acceptance。

## 主要位置

| 路徑 | 責任 |
| --- | --- |
| `XBrainLab/ui/main_window.py` | 主視窗、top navigation、五個 panel 建立、assistant dock 入口。 |
| `XBrainLab/ui/panels/` | Dataset、Preprocess、Training、Evaluation、Visualization workflow UI。 |
| `XBrainLab/ui/core/base_panel.py` | panel 共同基底，保存 controller、main_window、observer bridges。 |
| `XBrainLab/ui/core/observer_bridge.py` | 將 backend `Observable` event 轉成 Qt signal。 |
| `XBrainLab/ui/components/agent_manager.py` | UI 與 assistant / LLM controller 的接線層。 |
| `XBrainLab/ui/components/assistant_command_dispatcher.py` | 把 assistant command 放進專用 Qt thread，管理 shutdown / retry ownership，不讓失敗 teardown 的 thread reference 被提前釋放。 |
| `XBrainLab/ui/components/info_panel_service.py` | aggregate info panel 的集中更新服務；product runtime 由 command/navigation/observer shared refresh 呼叫 `MainWindow.update_info_panel()` -> `notify_all()`，mock / compatibility context 才可直接訂閱 `data_changed` / `preprocess_changed`。 |
| `XBrainLab/ui/owned_operation_presenter.py` | 只呈現 backend-owned operation snapshot，轉送 cancel intent，並防止較舊 operation 更新目前 control / status。 |
| `XBrainLab/ui/chat/` | in-app assistant 的 chat UI。 |

## 啟動與主視窗

`MainWindow` 接收一個 `Study` instance，並把它保存為 `self.study`。

初始化流程主要在 `XBrainLab/ui/main_window.py`：

1. 建立 top bar，加入五個 navigation buttons：Dataset、Preprocess、Training、Evaluation、Visualization。
2. 建立 `InfoPanelService(self.study, observe_controller_events=False)`，讓後續 sidebar 中的 aggregate info panel 可以註冊更新。
3. 建立 `QStackedWidget`。
4. 呼叫 `init_panels()` 建立五個 lazy placeholders；panel 在第一次開啟時才 materialize。
5. 呼叫 `init_agent()` 建立 assistant dock 與相關 signal wiring。

Product materialization 的順序就是 navigation index：

| index | panel | product constructor wiring |
| --- | --- | --- |
| 0 | `DatasetPanel` | `parent` + `ApplicationViewPublicationPort` |
| 1 | `PreprocessPanel` | `parent` + `ApplicationViewPublicationPort`；render query 從 real Study parent 解析 `ApplicationUiRuntime` |
| 2 | `TrainingPanel` | explicit query/publication/action ports + `TrainingTransientProgressPort` |
| 3 | `EvaluationPanel` | explicit `EvaluationQueryPort` + publication subscription port + `EvaluationActionPort` |
| 4 | `VisualizationPanel` | explicit query/publication/action ports |

Dataset / Preprocess 的 standalone、mock 或 no-runtime constructor 仍可在沒有
`publication_port` 時使用 `get_controller_for_compatibility_context()`。這是 test/compatibility
邊界，不是 product wiring。

`switch_page(index)` 切換 `QStackedWidget` 後，會委派
`XBrainLab.ui.refresh_coordinator.refresh_after_navigation()` 依 navigation index 刷新目標
panel、aggregate info panel 和 assistant backend status。因此 tab-switch refresh 的 panel mapping
與 shared status refresh 不再散在 `MainWindow` 內。Navigation refresh 現在也有 same-main-window
re-entrancy guard，避免 nested tab-switch refresh 對同一個 main window 重複刷新。Product command
result 只負責 structured feedback，不會建立第二套 state repaint；state-changing render 由
revisioned `ApplicationViewPublication` 提交。Training 的 live progress/event 和 non-`Study`
compatibility observer 是明確例外，不可成為 readiness 或完成狀態 truth。
頁面切換完成後，`MainWindow` 會立即並在下一個 Qt event-loop turn 重繪 nav 與 current panel，
避免 XCB / WSLg 下 stacked-page transition 留下 partial backing store；human-like walkthrough 會以
main-nav 與 visible `RightPanel` 像素 guard 保護這個可見 regression。
`BasePanel._create_refresh_bridge()` 只保留給 non-`Study` compatibility；Training product progress
由 transient port、五個 product panels 的 state subscription則直接接 application publication
port。Async command 的 `on_result` callback 只能處理 result message、
status 或錯誤顯示；不可在 callback 裡呼叫 `update_panel()`、`update_info()`、
`mark_refresh_dirty()` 等本地 state render refresh。`MainWindow.update_info_panel()` 現在委派到 `InfoPanelService.notify_all()`，
所以 coordinator 的 shared info refresh 會更新所有已註冊 sidebar aggregate panels；只在沒有
`info_service` 的 injected / compatibility context 下才 fallback 到 direct `info_panel.update_info()`。

## Controller 取得方式

`Study.get_controller()` 在 `XBrainLab/backend/study.py` 中實作 controller cache。
第一次要求某類 controller 時建立 instance，之後回傳 cached instance。

Product `MainWindow` 不呼叫 `Study.get_controller()`，也不建立 controller bootstrap bundle。
部分 panel constructor 的舊 `parent.study.get_controller(...)` fallback 已改成
`get_controller_for_compatibility_context()`，只在 mock / compatibility non-`Study` context 回傳 controller；
real `Study` panel 若缺少 typed product port，不會自行走回 controller tree。Training product
progress 來自 narrow transient port；直接 controller lookup 被限制在 outer compatibility
adapters，architecture guards 不允許 MainWindow product bootstrap 回流。
2026-05-14 後，`EvaluationPanel` 和 `VisualizationPanel` 的 training observer bridge 也不再從
`controller.study.get_controller("training")` 取得 fallback controller；沒有 injected training
controller 的 standalone context 只是不建立 training lifecycle bridge。

## ApplicationService Readiness Gate

`XBrainLab/ui/application_capabilities.py` 是 UI 進入 command spine 的主要薄 adapter。
它負責從 nearest `main_window.study` 取得 `ApplicationService`，提供 capability lookup、
blocked reason copy、command execution、post-command refresh，以及 mock / compatibility fallback
邊界。

### 已接上的高價值 path

| UI area | Backend truth | 現況 |
| --- | --- | --- |
| Data Import / recipe | `scan_source`、`preview_interpretation`、`validate_interpretation`、`apply_interpretation`、`reload_interpretation_recipe` | real `Study` 走 command sequence；BIDS label-field 建議顯示 selected-run bounded evidence，不從單一 run 或 UI 欄位順序猜測。direct file import fallback 只留給 no-service mock / compatibility context。 |
| Dataset edit actions | `update_metadata`、`apply_smart_parse`、`remove_files`、`import_labels` | confirmed mutation 走 command；table render 和 channel dialog 在 real `Study` 讀 `QueryStateCommand(data_lists)`。Dataset sidebar 不再提供 Reset Session。 |
| Preprocess / epoch | `preprocess`、`create_epoch` | filter / resample / rereference / normalize / epoch 走 owned command；epoch dialog 只讀 reviewed import handoff 綁定的 context。Visible action / status bar 顯示 matching operation stage，Cancel 後同一 workflow 可重試。 |
| Dataset split / training config | `configure_dataset_split`、`clear_datasets`、`configure_training` | split Confirm 只保存 specification / fingerprint / preview receipt；model selection 與 training settings defaults 不再以 stale controller echo 判定 service success。 |
| Training | `train`、`stop_training` | enabled capability 直接 dispatch confirmed owned command；Stop 是 lock-independent control acknowledgement，terminal state仍由 matching training publication 決定。controller running checks 只在 no-capability fallback。 |
| Evaluation / visualization / saliency | `evaluate`、`visualize`、`saliency` | Model Summary、metrics、Saliency publication 與 render preparation 在 background work 執行，以 request / generation / producer identity 擋 stale result。Training terminal 不自動算 Saliency；visible `Compute Saliency` 是唯一 product admission。 |
| Montage | `QueryStateCommand(state)`、`apply_montage` | dialog channel defaults 走 state query；confirmed positions 走 `ApplyMontageCommand`；picker/matching 仍是 UI request。 |
| Chat diagnostics | `ApplicationViewPublication` | assistant status、decision context、tool policy 讀同一 generation 的 state/capability，不把 missing capability 顯示成 debug error。 |

MainWindow close 先 fence application work、送出 cancellable-operation intents，再等待 backend
registry、training/evaluation/saliency/render workers、Qt owners 與 product subprocess inventory 收斂。
這條路徑不得在 Qt thread 阻塞等待 shared command lock；等待逾時會拒絕 clean-close claim，而不是
把仍存活 worker 當成成功。這是 source contract，仍需 canonical native lifecycle evidence 與 Windows
native lifecycle acceptance。

Data Splitting dialog 的 `Confirm` 成功只代表 lightweight specification 已保存；UI 不得顯示成
datasets、masks 或 training tensors 已建立，也不在此時清除既有 trainer。使用者按下
`Start Training` 後，application layer 才 materialize / audit split；失敗結果由 Training surface
顯示並保留原本可用狀態。

Training Setting 的 recommended values 是 backend deterministic starting point。Dialog 對 epochs、
batch size、learning rate、optimizer、evaluation strategy 分別追蹤 trusted user edit；context 變更
重新套 recommendation 時，只更新仍屬 recommended provenance 的欄位。UI 沒有 timed
hyperparameter search、trial progress 或 automatic model-selection contract，也不可用文案暗示已有。

### Assistant refresh 與 UI request

- `One Step` 每次最多執行一個可執行 command；`Workflow` 可繼續到真正需要 confirmation、
  `decision_needed` 或既有 UI dialog 的邊界。
- assistant command 開始時由 `AgentManager` 呼叫 shared observer suppression；完成後只依
  `ToolCommandResult.changed_state` 的 serialized scope 刷新，不另外維護第二套 panel truth。
- montage、Data Import、epoch、split、training setting、saliency setting 等人類決策沿用既有 UI
  surface。UI request 打開後 workflow 停在明確 waiting state，不在 chat 裡重做第二套表單。
- MainWindow 關閉時若 assistant worker 尚未安全停止，會拒絕第一次 close 並重試 teardown；
  不會在仍存活的 QThread 上直接銷毀 worker/QTimer。
- QThreadPool command 的 result/error 綁到 owner-child QObject receiver；owner 被 Qt 刪除時 queued
  delivery 自動斷線。獨立 cleanup receiver 保留到 terminal `finished`，才解除 observer
  suppression、busy state 與 active-worker ownership，避免 pytest-qt/WSLg teardown 的 native crash。
- worker thread 結束時由 Qt owner-thread lifecycle 執行 `deleteLater()`；UI 只讀 controller 發布的
  runtime snapshot，不再讀 worker/engine internals。architecture guard 保護這條邊界。

### Guarded boundary

- UI product methods 不可直接呼叫 `run_controller_compatibility_call()`；fallback 必須收在
  `_compatibility_*` helper 或明確 compatibility adapter boundary。
- 有 backend capability 的 command path 不可用 `controller.is_training()`、`has_datasets()`、
  `get_trainer()`、`validate_ready()`、`has_model()`、`has_training_option()` 重新 gate real
  `Study` readiness。
- service success path 不可再讀 `TrainingController.get_model_holder()` 這類 controller echo
  重新判定 command success。
- `main_window.py` 不得 direct `study.get_controller(...)` 或重新建立 controller bootstrap
  bundle；product panel materialization 只允許 typed ports。
- product-success integration tests 不可用 `BackendFacade`、controller compatibility helper、direct
  mutable `Study` state、positive `study.get_controller()` assertion、no-crash / generic string
  當成功證據。
- Visualization UI 不可呼叫 `get_trainers()`、`get_plans()`、`get_eval_record()`、
  `get_dataset()` 或保存 live Trainer/Plan/EvalRecord/Dataset；architecture guard 要求它只保存
  typed identity 與 immutable Application/render publication。

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
handler。TrainingPanel 的 high-level callbacks 只保留不可替代的本地副作用，例如清 log、
切 stop button、寫 status，render / readiness refresh 則交給 `refresh_after_observer()`，讓
aggregate info panel、assistant backend status 和 downstream analysis panels 不必等下一個
command result 或 tab switch；`training_updated` 是 live-tick 例外，仍保留 live `update_loop()`，
但不 fan-out 到 Evaluation / Visualization。
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
| `DatasetPanel` | revisioned application publication | publication owns loaded-data rows、capability 與 workflow state；import result 只顯示 acknowledgement / warning |
| `PreprocessPanel` | revisioned application publication | publication owns loaded/preprocessed render state與 readiness |
| `TrainingPanel` | revisioned application publication；transient `training_updated` progress | publication owns Start/Stop、terminal outcome、history 與 readiness；`training_updated` 只更新 live progress，不改 application revision 或 state controls |
| `EvaluationPanel` | revisioned application publication | publication owns available result identities、controls 與 render readiness |
| `VisualizationPanel` | revisioned application publication | publication owns saliency provenance、available plots、montage 與 render readiness |

Real `Study` product path 的五個 panel 都以 typed query/publication/action ports 接到
ApplicationService；state-changing render 只認 revisioned application publication。
command-result callback 只顯示 acknowledgement、error 或 in-flight feedback，不得直接
refresh workflow state，也不得改 Start/Stop、readiness、terminal outcome 或 history。
mock / standalone compatibility path 仍可讀 controller getter，但不能成為 real product
success truth。Training 的 `training_updated` 是唯一分離的 transient progress channel，
不會改 application revision 或 publication-owned controls。

`EvaluationPanel` 的 Model、Run 與 Split selector 共同建立 generation-bound render request。
Split 清單只呈現該 repeat 實際保存的 predictions；Average 則使用所有 completed repeats 的
共同 split。切換 selector 會先清除舊 metrics，再提交 exact split render。`Show percentages`
只重畫 confusion matrix 的 true-label row normalization，不改 Precision、Recall、F1 或
Support。

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
- 需要 compatibility montage apply fallback 時，透過 explicit mock / compatibility helper 取得 preprocess
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
- 第一層 UI 不顯示 raw command names，例如 `load_data`、`configure_training`；主介面顯示
  `Load EEG data`、`Train model` 這類使用者語言。Reset Session 已從 desktop surface 移除；raw command
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
mock / compatibility fallback boundary 和 refresh policy。

若以 mock / compatibility non-`Study` context 單獨建立並允許 observer events，`InfoPanelService` 可透過
`get_controller_for_compatibility_context()` 建立 compatibility observer bridge：

- dataset controller 的 `data_changed`
- preprocess controller 的 `preprocess_changed`

事件發生後，service 會透過 `QueryStateCommand(query="data_lists")` 取得 detached
`raw_rows` / `preprocessed_rows`，並呼叫已註冊 info panel 的 `update_info(...)`。
Product command 不提供 `include_objects` opt-in。real `Study` query 失敗時會回空 summary
並記 log，不會 fallback 到 controller list reads；mock / compatibility non-`Study`
context 才保留 controller-list compatibility fallback。listeners 使用 `weakref.WeakSet`
保存，以降低已刪除 widget 被長期持有的風險。

## 現況邊界

目前 UI 架構可以交接為：

- `MainWindow` 是 shell，負責 top navigation、stack、五個主要 panel、assistant 入口。
- 五個 product panels 由 typed query/publication/action/transient ports 建立；Training transient
  progress 不代表 workflow state truth。
- `BasePanel` / `QtObserverBridge` 仍服務 compatibility context 與 publication delivery，但
  action / readiness / product-success truth 必須回到 command / query。
- `AgentManager` 是 assistant 與 UI 的接線層，不是 backend truth owner。
- `InfoPanelService` 集中處理 aggregate info 的跨 panel 更新；real `Study` data-list summary
  走 `QueryStateCommand(data_lists)`。

需要注意的是，這不是 repo-wide zero-controller。Mock / compatibility adapters 仍可使用
explicit controller fallback，部分 constructor signatures 也尚未縮窄。
`InfoPanelService` 在 real `Study` runtime 已不再建立 direct controller bridge，但這只是
aggregate-info lookup cleanup，並不代表 UI controller observer 已全部退出。因此後續
cleanup 應先把 standalone tests 改成 typed fixtures，再移除不再需要的 compatibility
parameters/helpers；不可讓它們回流為 product path。
