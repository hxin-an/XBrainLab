# UI 目前架構

最後更新：`2026-09-08`

## 範圍

這份文件描述 XBrainLab 目前已從 source 確認的 PyQt UI 架構，重點是
`MainWindow`、五個主要 workflow panel、observer refresh、assistant 接線，以及
aggregate info 更新方式。

本文不把未驗證的理想分層寫成既有事實。現況上，五個 product panels 都由
ApplicationService-backed typed ports 建立；Training 的 live progress 由 narrow transient port
傳遞，不再由 MainWindow 注入 controller bundle。Workflow controller fallback 已移除；Assistant lifecycle controllers
仍有不同責任，不能把這些情況混為 repo-wide zero-controller。

## Runtime boundary

五個 product panels 的資料讀取、readiness 與 state render 使用 `ApplicationService` 的
query / publication ports；Training live progress 另用 narrow transient port。Dataset、
Preprocess、Training、Evaluation 和 Visualization 不從 workflow controller 讀取或修改
EEG / training state。TrainingSettings 與 Saliency Settings 從 detached snapshot 讀初值；
Model Selection 從 query port 讀 signal context。缺少必要 publication/query 時 fail closed，
不回到 controller mutation。

`ApplicationViewPublication` 原子綁定 state、capability 和 detached rendering data。Panel 的
render ledger 只在成功 render 後提交 revision，失敗保留可重試狀態；navigation refresh 和
transient progress 不取代 publication-owned readiness / terminal truth。取消與長工作進度由
backend-owned operation identity 決定，UI presenter 只呈現狀態與轉送 cancel intent。

Preprocess native plot lifecycle 仍有必要的 close boundary：暫時 close 保留恢復能力，terminal
shutdown 解除 timers、signal proxies 與 native plot resources。不能把 teardown protection
當成冗餘 observer wiring 刪除。

這不是 repo-wide zero-controller：Assistant 的 ChatController / LLMController 是有效的
conversation / turn lifecycle owner。沒有 product caller 的三個 EEG controller adapters 已退役。不能以刪除
workflow controller fallback 推論所有 controller 都應刪除，也不能把 mock-only pass 當
Windows native acceptance。

## 主要位置

| 路徑 | 責任 |
| --- | --- |
| `XBrainLab/ui/main_window.py` | 主視窗、top navigation、五個 panel 建立、assistant dock 入口。 |
| `XBrainLab/ui/panels/` | Dataset、Preprocess、Training、Evaluation、Visualization workflow UI。 |
| `XBrainLab/ui/core/base_panel.py` | panel 共同基底，保存 parent context、publication/transient bridges 並管理 cleanup。 |
| `XBrainLab/ui/core/observer_bridge.py` | 將 backend `Observable` event 轉成 Qt signal。 |
| `XBrainLab/ui/components/agent_manager.py` | UI 與 assistant / LLM controller 的接線層。 |
| `XBrainLab/ui/components/assistant_command_dispatcher.py` | 把 assistant command 放進專用 Qt thread，管理 shutdown / retry ownership，不讓失敗 teardown 的 thread reference 被提前釋放。 |
| `XBrainLab/ui/components/info_panel_service.py` | 只 render/replay publication-owned aggregate rows；不建立 controller observers 或額外 query。 |
| `XBrainLab/ui/components/modal_presentation.py` | blocking alert／confirmation 的共用 presentation；caller仍擁有copy、confirmation policy與後續mutation，dialog只負責severity、compact geometry、long-text scroll與安全按鍵預設。 |
| `XBrainLab/ui/owned_operation_presenter.py` | 只呈現 backend-owned operation snapshot，轉送 cancel intent，並防止較舊 operation 更新目前 control / status。 |
| `XBrainLab/ui/chat/` | in-app assistant 的 chat UI。 |

## 啟動與主視窗

`MainWindow` 接收一個 `Study` instance，並把它保存為 `self.study`。

初始化流程主要在 `XBrainLab/ui/main_window.py`：

1. 建立 top bar，加入五個 navigation buttons：Dataset、Preprocess、Training、Evaluation、Visualization。
2. 建立 `InfoPanelService()`，讓後續 sidebar 中的 aggregate info panel 可以註冊更新。
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

所有 workflow panel 與 BasePanel/BaseDialog constructor 不再接受 workflow controller。
沒有可用 publication/query 時維持 unavailable /
blocked，不建立相容執行路徑。

`switch_page(index)` 切換 `QStackedWidget` 後，會委派
`XBrainLab.ui.refresh_coordinator.refresh_after_navigation()` 依 navigation index 刷新目標
panel，不額外拉取 aggregate info 或 assistant backend status。Navigation refresh 有 same-main-window
re-entrancy guard，避免 nested tab-switch refresh 對同一個 main window 重複刷新。Product command
result 只負責 structured feedback，不會建立第二套 state repaint；state-changing render 由
revisioned `ApplicationViewPublication` 提交。Training 的 live progress/event 不可成為 readiness
或完成狀態 truth。舊 command-result/observer router 與 suppression/replay state 已移除。
頁面切換完成後，`MainWindow` 會立即並在下一個 Qt event-loop turn 重繪 nav 與 current panel，
避免 XCB / WSLg 下 stacked-page transition 留下 partial backing store；human-like walkthrough 會以
main-nav 與 visible `RightPanel` 像素 guard 保護這個可見 regression。
Training product progress 由 transient port、五個 product panels 的 state subscription 直接接 application publication
port。Async command 的 `on_result` callback 只能處理 result message、
status 或錯誤顯示；不可在 callback 裡呼叫 `update_panel()`、`update_info()`、
`mark_refresh_dirty()` 等本地 state render refresh。`MainWindow.update_info_panel()` 現在委派到 `InfoPanelService.notify_all()`，
它重播已發布 rows 給已註冊 sidebar aggregate panels，不另設 direct widget refresh fallback。

## Controller 與 application context

Product `MainWindow` 不呼叫 `Study.get_controller()`，也不建立 controller bootstrap bundle。
原本給 standalone tests 使用的 controller lookup/execution helpers 已移除。Typed ports
維持 command/query 和非同步 publication 的邊界；Assistant conversation/turn controllers
不是 EEG workflow mutation owner。

## ApplicationService Readiness Gate

`XBrainLab/ui/application_capabilities.py` 是 UI 進入 command spine 的主要薄 adapter。
它負責從 nearest `main_window.study` 取得 `ApplicationService`，提供 capability lookup、
blocked reason copy、command execution 和 owned asynchronous lifecycle；state repaint 則由
publication renderer 擁有。

### 已接上的高價值 path

| UI area | Backend truth | 現況 |
| --- | --- | --- |
| Data Import / recipe | `scan_source`、`preview_interpretation`、`validate_interpretation`、`apply_interpretation`、`reload_interpretation_recipe` | real `Study` 走 command sequence；BIDS label-field 建議顯示 selected-run bounded evidence，不從單一 run 或 UI 欄位順序猜測。direct file import fallback 已移除。 |
| Dataset edit actions | `update_metadata`、`apply_smart_parse`、`remove_files` | confirmed mutation 走 command；table render 和 channel dialog 在 real `Study` 讀 `QueryStateCommand(data_lists)`。Dataset sidebar 不再提供 Reset Session。 |
| Preprocess / epoch | `preprocess`、`create_epoch` | filter / resample / rereference / normalize / epoch 走 owned command；epoch dialog 只讀 reviewed import handoff 綁定的 context。Visible action / status bar 顯示 matching operation stage，Cancel 後同一 workflow 可重試。 |
| Dataset split / training config | `configure_dataset_split`、`clear_datasets`、`configure_training` | split Confirm 只保存 specification / fingerprint / preview receipt；model selection 與 training settings defaults 不再以 stale controller echo 判定 service success。 |
| Training | `train`、`stop_training` | enabled capability 直接 dispatch confirmed owned command；Stop 是 lock-independent control acknowledgement，terminal state仍由 matching training publication 決定。沒有 capability 時 fail closed。 |
| Evaluation / visualization / saliency | `evaluate`、`visualize`、`saliency` | Model Summary、metrics、Saliency publication 與 render preparation 在 background work 執行，以 request / generation / producer identity 擋 stale result。Detached Evaluation render不呈現user-owned Cancel；Training terminal不自動算 Saliency，visible `Compute Saliency` 是唯一 product admission。Evaluation-admitted但未計算的Fold仍列出並fail closed到Compute提示。 |
| Electrode Layout | `QueryStateCommand(state)`、`apply_montage` | Dataset sidebar 在 `Channels` 正下方提供唯一可見入口；它先顯示目前 layout summary，再於同一 dialog 展開 standard-layout mapping。使用者先以 Channels 排除不需要的 channel；Apply／Replace Layout 僅在所有保留 channel 映射有效、唯一電極且可畫頭皮圖時開放，問題列與簡短摘要同步更新。confirmed replace／restore 才走 `ApplyMontageCommand`；restore 也由 backend 在 mutation 前驗證完整 coverage。BIDS ready geometry 可在同一 import 內由 retained reviewed snapshot 回復；新 import／reset 會清除此能力。匯入 partial metadata 不阻擋資料匯入、不改變資料軸，但不構成空間圖 readiness；3D 另依幾何條件開放。 |
| Chat diagnostics | `ApplicationViewPublication` | assistant status、decision context、tool policy 讀同一 generation 的 state/capability，不把 missing capability 顯示成 debug error。 |

Model Selection dialog只render `ModelCatalog`的detached projection：search可匹配name、stable ID、alias、
family與task；disabled row顯示catalog-owned reason且不能Confirm。Provider readiness在Python-owned background
worker做bounded preflight；完成前不阻塞Qt thread。Healthy provider顯示upstream IDs並收起正常狀態提示；
unavailable provider顯示recovery banner與distinct `legacy.braindecode.*` IDs，並保留原selection，不自動
替換identity。Dialog不提供部分model-specific constructor參數的文字編輯器；Confirm使用catalog reviewed
defaults，typed `model_params` contract仍由training command與resource／artifact owners保留。Backend在
`ConfigureTrainingCommand` mutation前以當下Epochs signal context重新admit，因此stale UI projection不能
繞過dataset compatibility。

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

- UI product methods 不可呼叫 controller compatibility helper；workflow state 只讀 typed
  publication/query boundary，缺少它時 fail closed。
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

主要 panel 繼承 `BasePanel`，它負責：

- 從 parent 推導 `self.main_window`
- 保存 `_bridges`，讓 `QtObserverBridge` 在 panel 生命週期內不被釋放，並在
  `cleanup()` 時解除訂閱

`BasePanel` 不會在 base constructor 自動呼叫 `init_ui()` 或 `_setup_bridges()`。
各 panel 會先完成自己的 helper/component 初始化，再明確呼叫 `_setup_bridges()` 與
`init_ui()`。

State refresh 使用 revisioned publication 與既有 render ledger。Training 的
`training_updated` 只呼叫 live `update_loop()`，不 fan-out 到 Evaluation / Visualization。
BasePanel 的 `_create_bridge()` 保留訂閱生命週期；舊 simple-refresh helper 已移除。
Architecture guards 阻擋直接 observer repaint 與第二套 command-result refresh truth。

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
Workflow panel 不保留 controller getter fallback。Training 的 `training_updated` 是唯一分離的 transient progress channel，
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
- Montage apply 使用 command / reviewed UI handoff，不建立 preprocess controller fallback。
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
- 第一層 controls 收斂到固定右側 dock title bar：`XBrainLab`、new conversation、
  settings、hide。Assistant 不提供 float 或 left-dock；workflow / runtime
  details 放在 main status bar、tooltip、settings 或非 transcript diagnostics。
- 第一層 UI 不顯示 raw command names，例如 `apply_interpretation`、`configure_training`；主介面顯示
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
- `scripts/dev/capture_ui_baseline.py` 會產出 ignored `build/dev-artifacts/ui-baseline/*.png` live captures
  與exact-source `ui-baseline-evidence.json`，並比對 `tests/baselines/ui/` approved baseline；缺圖、
  source/reference hash drift、尺寸差異或超出pixel threshold都fail closed。top-level captures是local
  generated output，不再tracked；approved reference不由capture自動改寫。
- `scripts/dev/run_app_polish_ui_dpi_gate.py` 只接受Windows + Qt `windows` platform，依序建立
  100/125/150% app-polish evidence。每個scale沿用`capture_ui_polish_surfaces.py`的visible-control、
  text-fit、primary action、geometry、scroll與consecutive-frame contract；aggregate拒絕缺scale、
  observed DPR不符或stale source。這是automated Windows-runtime evidence，不等於真人DPI/多螢幕驗收。

目前仍未完成的 UI product evidence：

- Windows Desktop shortcut 人工 click-through 到 assistant 對話還沒完成。
- Montage picker / matching 與其他需要真人確認的 UI request 仍須適用的 native walkthrough；
  隱藏 post-load label dialog 已移除，external labels 由 Data Import review/apply 處理。
- Guarded UI product smokes / real-tools evidence 已不再以 direct mutable `Study` state read
  作為成功證據；其他 integration suites 的 fixture/setup 型 direct state access 還需要分批判讀，
  不能一概當作 product acceptance。
- reset / new session 的 destructive confirmation 還需要完整 product walkthrough。

## Aggregate Info 更新

`MainWindow` 建立單一 `InfoPanelService()`，各 `AggregateInfoPanel` 以 weak listener
註冊。Service 不持有 Study，只 render/replay `ApplicationViewPublication.data_summary_rows`，不另發
`QueryStateCommand(data_lists)`，也不訂閱 controller events。沒有 usable publication 時
呈現空的 fail-closed summary；deleted Qt listener 會被移除，其他 render failure 則回報失敗，
讓 owning publication renderer 決定是否提交 revision / retry。

## 現況邊界

目前 UI 架構可以交接為：

- `MainWindow` 是 shell，負責 top navigation、stack、五個主要 panel、assistant 入口。
- 五個 product panels 由 typed query/publication/action/transient ports 建立；Training transient
  progress 不代表 workflow state truth。
- `BasePanel` / `QtObserverBridge` 負責 publication/transient delivery 和 cleanup，但
  action / readiness / product-success truth 必須回到 command / query。
- `AgentManager` 是 assistant 與 UI 的接線層，不是 backend truth owner。
- `InfoPanelService` 集中 render publication-owned aggregate rows，不建立第二份 query truth。

Assistant conversation/turn controllers 仍存在；清理不能破壞現有 publication、native teardown 或
Assistant lifecycle。是否能交付仍以同版本 handoff gates 與使用者 native acceptance 判斷。
