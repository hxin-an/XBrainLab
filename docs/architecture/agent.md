# Agent 目前架構

最後更新：`2026-08-18`

## 範圍

這份文件只描述 XBrainLab 內建 assistant 的目前架構。Approved重構目標由
[Agent target](../target/agent.md)擁有；本文件不建立第二份target。

這裡的 agent 指 app 內的 workflow-aware software operation agent，不是外部開發用的 Codex。

## 一句話

目前 assistant 不是單純聊天視窗，而是已經能透過 tool call 操作 XBrainLab workflow 的功能層。

目前實際路徑是：

```text
ChatPanel
  |
  v
AgentManager (Qt composition / presentation adapter)
  |
  +--> AssistantRuntimeLifecycle / RuntimeCoordinator
  +--> AssistantCommandDispatcher / AssistantCommandThread
  +--> AssistantApplicationPublicationCoordinator
           |
           v
       LLMController
           |
           +--> AssistantTurnOrchestrator
           +--> AssistantToolAttemptSession
           +--> ProcessRAGRetrieverLifecycle
           +--> AgentWorker / LLMEngine
           +--> Parser / VerificationLayer / ToolAttemptCoordinator
           +--> ToolExecutionCoordinator
  |
  v
Real Tools
  |
  +--> ApplicationService capability policy / direct command execution
  |
  v
ApplicationService / Command API
  |
  +--> Study-scoped command/state lifecycle and focused services
  |
  v
Study / managers / domain state
```

這是一個可工作的中間狀態，但還不是最終理想架構。

## 主要位置

| 區域 | 目前責任 |
| --- | --- |
| `XBrainLab/ui/chat/` | chat panel、使用者輸入、模型 / 執行模式 UI。 |
| `XBrainLab/ui/components/agent_manager.py` | UI 和 assistant 的 composition/presentation adapter；組合窄 lifecycle、dispatcher、publication 與既有 UI handoff owners。 |
| `XBrainLab/ui/components/assistant_command_dispatcher.py` | assistant controller thread ownership、queued shutdown、timeout retry 與 lifecycle cleanup。 |
| `XBrainLab/ui/components/assistant_runtime_lifecycle.py` | local runtime activation、terminal close、recoverable error 與 immutable runtime state。 |
| `XBrainLab/ui/components/assistant_application_publication_coordinator.py` | 將 revisioned application publication 與 training terminal notice 投影到 Assistant。 |
| `XBrainLab/llm/agent/controller.py` | 組合 agent turn：context、parser、verification、confirmation 與 bounded tool execution；不再保存 writable lifecycle aliases。 |
| `XBrainLab/llm/agent/turn_orchestrator.py` | `AssistantTurnOrchestrator` 擁有 host/RAG/generation/cancellation correlation；`AssistantToolAttemptSession` 擁有 request-scoped counters、visible feedback 與 repeated proposal history。 |
| `XBrainLab/llm/agent/rag_process_lifecycle.py` | RAG retriever subprocess 的啟動、timeout、終止與結果 ownership。 |
| `XBrainLab/llm/agent/tool_execution_coordinator.py` | 執行單一已驗證 tool、套用 capability gate、正規化 command result、記錄 metrics 與發出 command lifecycle signal。 |
| `XBrainLab/llm/agent/worker.py` | 背景 thread 中的 LLM 初始化、生成、timeout、model switch；只用 immutable runtime snapshot 對 UI 發布狀態。 |
| `XBrainLab/llm/core/` | local-only backend selection、local backend、runtime config、local model catalog。 |
| `XBrainLab/llm/tools/` | tool definitions、registry、real tools。 |
| `XBrainLab/llm/rag/` | RAG retriever 與 prompt context 補充。 |

## 目前分層

### 1. Chat UI

`ChatPanel` 主要是 UI component。

它負責：

- 發出使用者訊息。
- 發出停止生成、模型切換、執行模式切換等 signal。
- 顯示 local runtime 狀態；model menu 不再提供 Gemini/API 產品選項。
- debug 模式下可觸發測試用 tool command。

它不應該直接懂 backend workflow。

### 2. AgentManager

`AgentManager` 是 UI 和 agent runtime 的 composition/presentation adapter。

它負責：

- 透過 runtime lifecycle 與 command dispatcher 建立、啟動及關閉 `LLMController`，而不是直接擁有 worker process 細節。
- 將 chat panel 的 typed turn 交給 dispatcher，並將 assistant presentation、activity 與錯誤狀態送回 UI。
- 透過既有 UI handoff host 處理 switch panel、montage、設定與 confirmation，不在 chat 裡建立第二套 workflow form。
- 透過 `LLMConfig.normalize_backend_mode()` 把 UI label 對齊 runtime key。
- 以 `ApplicationViewPublication.revision` 確認 GUI 已套用哪一份 backend state；只有 matching
  revision acknowledgement 後，才接收該 publication 保留的 terminal lifecycle event。

UI side effect 仍由 structured tool result 的 UI request 交給 `AgentManager`，但會沿用既有 dialog；
request 打開後 workflow 會停止並顯示 waiting state，不會繼續猜測使用者選擇。

### 3. LLMController

`LLMController` 是 agent turn 的組合層；mutable lifecycle 已有明確 owner。

它負責：

- 建立 `ToolRegistry` 並註冊 real tools。
- 組prompt：strict policy、stage-published target schemas、minimal state card、bounded RAG、最新user與
  最多上一則Assistant-visible訊息。
- 讓 `AgentWorker` 在 background thread 生成回覆。
- 用`CommandParser`只接受exact三欄JSON envelope；不做寬鬆抽取或legacy fallback。
- 用 `VerificationLayer` 檢查 registered tool schema、required parameter、JSON-like type、
  enum、confidence 和部分資料範圍。
- 套用 ApplicationService capability gate，避免 assistant 在錯誤 backend state 呼叫不該開放的工具。
- 將已驗證的單一 tool 交給 `ToolExecutionCoordinator`；mapped workflow tool 透過
  `execute_application_tool_command(...)` 執行 ApplicationService command，直接取得
  `CommandResult` payload。
- tool command lifecycle signal 只更新 Assistant 的 working / terminal presentation。Product
  workflow panels 由 revisioned `ApplicationViewPublication` 更新，不以 serialized
  `changed_state` 另做一次 repaint；command 完成後 agent 會重讀同一份 ApplicationService
  state / capability publication。
- 處理 destructive / long-running tool 的 human confirmation。
- 每個user turn只允許一個tool或一個`respond_to_user`；terminal後不continuation。

Controller 不再透過 `_active_generation_id`、`_retry_count` 等 writable compatibility alias 保存
第二份狀態。Host/RAG/generation/cancellation correlation 只在 `AssistantTurnOrchestrator`；format
retry、tool failure/execution、visible response 與 repeated proposal history 只在
`AssistantToolAttemptSession`。Architecture gate 會以 AST 同時掃 production controller 與測試
fixture，避免測試寫入無效 instance attribute 後產生假通過。

UI 不可直接讀 `AgentWorker.engine` 或 generation thread。worker 只發出 model id、backend mode
與 initialized 狀態的 snapshot；`AgentManager`、VRAM conflict check 和 model deletion preflight
都讀 `LLMController.runtime_snapshot()`。architecture guard 會阻擋 UI 回到 worker internals。

這一層目前同時包含 agent orchestration 和一部分 workflow policy。所有 mapped workflow
command 仍由同一個 Study-scoped ApplicationService lock 序列化，避免 UI 與 assistant 同時 mutation。

### 執行模式

產品沒有execution-mode selector，也沒有Host推導的step-by-step／continuation scope。每個user turn
由Granite輸出一個strict decision envelope；Host只驗證、要求必要confirmation、執行一個approved
action並顯示trusted terminal。成功、blocked、cancelled或failed都結束turn，下一步必須由使用者再發
一則訊息。

### Prompt state projection

目前prompt不使用Host intent narrowing、recommended-next-step或deterministic continuation。
`ContextAssembler`從同一份immutable `ApplicationViewPublication`投影backend-owned stage與最小state
card，再依`STAGE_CONFIG`發布該stage的approved target schemas。模型只在這個集合中選一個tool，
或使用`respond_to_user`；Host不替模型選前置步驟或自動接續下一個mutation。

Prompt history只保留最新user訊息與最多一則Assistant-visible訊息，並排除`Tool Output:`、structured
envelope與內部system payload。RAG example也只能在同一stage的approved tool集合中檢索，不能授予
capability、confirmation或continuation權限。

Data Import對模型是單一零參數`import_eeg_data` GUI completion tool。內部scan、preview、validate、
apply與recipe lifecycle仍由既有Data Interpretation/ApplicationService owner負責，不作為模型工具，
也不在chat中建立第二套import state machine。

### Data / training decision boundary

- BIDS label-field recommendation 和其 selected-run evidence 來自 Data Interpretation command
  result。Assistant 可以解釋 evidence 或開啟既有 review surface，但不能自行把 `trial_type` /
  `value` 規則、第一個 run 或聊天文字升格成 confirmed truth。
- `create_epochs`、`configure_dataset_split`、`select_model`與`configure_training`只是零參數GUI
  completion request；參數與preview由既有dialog owner收集，模型不代填。
- Dataset split UI保存typed split specification與preview receipt。完成設定不代表training tensors已
  建立；`start_training`仍由ApplicationService觸發materialization、audit與resource preflight。
- Deterministic training recommendation 由 backend contract 產生。只有 trusted UI host 可附加
  per-field user-edit provenance；Assistant 不可從自然語言或 tool payload 偽造 manual ownership。
  Timed hyperparameter search 尚無 tool schema，也不是可執行能力。

### 4. Worker / Engine / Backend

`AgentWorker` 和 `LLMEngine` 負責 LLM runtime。

目前產品 runtime 是 local-only assistant：

- local model backend。
- 不依賴 API key。
- 不把 Gemini/API 當成產品 execution mode。
- 優先讓本地模型、模型 cache、GPU/CPU execution 可理解、可測、可交接。
- 模型選型不使用中國公司或中國來源模型。
- Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 等模型不列入 product / legacy 選型。
- 優先考慮非中國來源、授權清楚、可本地部署的模型。

2026-08-01 local runtime truth：

| role | model | provider | estimated download | cache status | smoke |
| --- | --- | --- | ---: | --- | --- |
| primary | `ibm-granite/granite-3.3-2b-instruct` | IBM | 5.08 GB | cached | prompt / structured / real GPU boundary workflow PASS |
| historical cache/evidence only | `microsoft/Phi-4-mini-instruct` | Microsoft | 7.69 GB | root checkout cache only | not selectable; older ChatPanel evidence only |
| historical evidence only | `microsoft/Phi-3.5-mini-instruct` | Microsoft | 7.64 GB | not required by current candidate | not selectable; no current full ChatPanel run |

每個 checkout 的已下載模型相容 cache 預設位於：

```text
XBrainLab/llm/core/models
```

產品 launcher 不依賴 Python 的 WSL-home default。它在啟動前明確設定模型與 RAG cache：
既有 canonical cache 可直接沿用，新安裝則使用 repo 所在 Windows 磁碟的
`XBrainLabCache/models` 與 `XBrainLabCache/rag`。這是 deployment/runtime policy；模型選擇、
quota 與 snapshot 驗證仍由 application-side catalog contract 決定。

Model cache facts are path-scoped. The closure worktree currently contains only exact Granite and
uses about `5.07 GB`; the root checkout used by the installed Desktop launcher contains about
`12.77 GB` because retired Phi content is still present there. Runtime evidence must record the
selected cache path, branch, full SHA, dirty state and model revision before either number is used.
Granite is the exact product primary. The real boundary artifact covers one model-owned scan, host-owned
parameter-free preview / validate continuation, typed Data Import review handoff, cancellation and
shutdown; it is not a long-session or raw-model accuracy claim.
Phi entries above document historical cache/evidence only. The product catalog accepts exact
Granite 3.3 2B; Phi cannot be selected and never becomes a fallback.
舊 Qwen cache 已刪除，catalog / architecture guards 會阻止被禁用來源重新進入 product path。

新增 runtime policy：

- `XBrainLab/llm/core/model_catalog.py` 是 local model allow-list / block-list / size policy 的單一來源。
- 下載前必須通過 `plan_model_download()`，限制單模型 10GB、總 cache 20GB。
- `AgentManager` first-run consent 會在首次啟用 local runtime 前顯示 GPU/CPU resource
  notice、download estimate、cache status，並提供 Enable / Download / Use existing cache /
  Later / Disable；app startup 不會自動載入大型 local model。
- runtime resolver 只啟動設定中明確選定且可用的 exact model；若不可用就回 typed unavailable，
  不靜默改用另一個 catalog model。
- `LocalBackend` 會阻擋未列入 product catalog 或被中國模型 policy 擋下的 repo id。
- `LocalBackend` 的 `trust_remote_code`、CUDA dtype、system-role 與 runtime context budget 都來自
  immutable catalog spec；本機 settings 不能放寬 remote-code trust。
- `LLMConfig` 會把舊 `INFERENCE_MODE=api` 或 settings 裡的 Gemini/API mode 讀成 `local`。
- `LLMEngine` 只會 instantiate `LocalBackend`；product package 已移除 remote backend modules。
- `AgentWorker.reinitialize_agent(...)` 只接受 `allowed_local_model_ids()` 裡的本地模型或 generic
  `Local`，其他模型名稱會 fail closed，不會 fallback 到 remote backend。
- `ModelSettingsDialog` 只保留 local model install/delete/activate 和 generation parameters，不再有
  remote key verification UI。
- `tests/architecture_compliance.py` 會靜態掃描 product path，禁止 remote backend class / key env path
  回到 `XBrainLab/`。

目前仍要保留在架構判讀中的 runtime 行為包括：

- runtime config reload。
- model / backend switch。
- generation timeout。

`LLMConfig` 和 `AssistantRuntimeSelection` 是 runtime truth。UI 顯示文字不能當成真實 backend 狀態。

目前只宣稱Granite固定正向selection suite的checkpoint。Host保留strict schema、stage/publication、
capability與confirmation verification，但不做intent narrowing或deterministic continuation。這種
工程evidence不能替代真人workflow或thesis accuracy，也不能把歷史`117/117`、`121/121`或Phi
candidate分數移植成Granite claim；candidate必須以同一frozen source完成48-case gate。
4-bit loading 仍是 optional path；`accelerate` / `bitsandbytes` 不是預設產品啟動硬需求。

Gemini/API 不再列為產品驗證目標；default dependencies 不包含 remote SDK。若歷史研究需要遠端
fixture，必須放在明確 optional legacy path，不能被 product code import。

### Chat Response Reliability Boundary

2026-05-02 人工驗收暴露出 agent/UI 邊界問題：local runtime smoke 通過，不代表
`ChatPanel -> AgentManager -> LLMController -> AgentWorker -> LLMEngine -> ChatPanel`
的 user-visible flow 一定可用。

已確認的可靠性缺口：

- 普通自然語言回覆只靠 streaming chunk 顯示；如果模型回空字串，舊邏輯會 finalize turn，
  但 transcript 沒有 assistant bubble。
- 若模型只輸出 tool-call JSON 且 tool 成功，raw JSON 會被隱藏，single mode 會 stop after
  success；舊邏輯可能沒有任何可見 tool summary。
- worker error / local unavailable 需要變成 chat transcript 中的 visible message，不可只停在
  status update。
- deterministic tool-call eval 不覆蓋普通 `hello` 這種 no-tool response path。

本輪修正後的 agent product contract：

- greeting與一般問答使用strict `respond_to_user` envelope，不執行替代工具。
- empty response 會發出 visible error，並讓 UI 回 idle。
- tool-only successful turn 會產生 user-facing visible summary。
- ApplicationService blocked command 會立即發出 shared blocked reason，但 transcript 不顯示
  raw tool name、backend command name 或 snake_case command。
- 缺少direct preprocess參數時使用`respond_to_user`精確詢問，不發明值、不改走GUI。
- tool error 會分成 input / precondition / runtime 等 product-level bucket；developer detail
  只留在 structured history / diagnostics / logs。
- busy re-entry 不會默默吃掉使用者輸入；UI 會提示 assistant still processing。
- tests 必須覆蓋 normal response、empty response、worker error、local unavailable first-open、
  missing argument、empty tool result、state-gated command、successful command summary。

### Agent Panel Product UI Contract

`ChatPanel` 只呈現 typed runtime / turn / response state，不自行推測 backend readiness：

- `AgentManager` header 將 runtime 與 turn state投影成 accessibility description、tooltip 與
  typed panel state；header 不顯示額外綠色／橘色 status badge。窄 dock 固定保留產品標題、
  New chat、Settings、Close。
- message area 擁有 loading、empty、transcript、activity、response action 與 confirmation card；
  composer 固定在底部 layout，不用 absolute positioning。Panel 不顯示 execution-mode selector。
- setting change 與高風險 action 使用 transient `AssistantConfirmationCard`。Card 持有原始
  `AgentConfirmationRequest`，Apply / Cancel 產生同 identity 的 typed
  `AgentConfirmationResolution`，不從顯示文字重建 command。
- action card 隱藏空對話狀態並佔用 transcript 流程；長到 12 列的設定仍由 message area
  垂直捲動，尾端不放 expanding spacer，確保 Cancel / Apply 在 320 px dock 可到達。
- current value 只讀同 generation、`state_reliable` 的 `ApplicationViewPublication`；publication
  generation 不同時會提示重新驗證，不從 panel widget 或 `Study` internals 建第二份狀態。
- `ApplicationViewEventPublisher` 將 terminal training lifecycle 綁定 publication revision。若
  Qt queued delivery 尚未確認該 revision，event 會保留；`QtObserverBridge` 回報 matching revision
  後才重試，避免 UI state 與 assistant terminal message 倒序或遺失。
- action 完成後，GUI 同步仍由 `application_command_completed -> changed_state -> shared refresh`
  處理；card 不直接寫 Training / Dataset widget。
- transcript 只有接近尾端時自動跟隨；使用者向上閱讀後，新訊息不可強制拉到底部。
- user / assistant bubble 使用同一個 content-aware 寬度契約，最大寬度受 viewport 限制；
  panel resize、streaming 和 100/125/150% scale 都要重新計算換行與高度。長 path / URL 可在
  word boundary 之外斷行，code block 自己水平捲動，不讓整個 transcript 產生 horizontal overflow。
- composer 是固定於底部的兩欄 layout：可增高的多行輸入使用剩餘寬度，Send / Stop action
  使用穩定 geometry。空輸入、loading、waiting 和 running state 只改 action semantics／enabled
  state，不讓按鈕與輸入框跳位。
- empty state 與 durable transcript 必須互斥；判斷依 message ownership，而不是 Qt
  `isVisible()`。即使 dock 暫時隱藏、背景收到 runtime refresh 或 confirmation cleanup，
  重新開啟後也不可把 suggestion empty state 插回既有對話。
- confirmation card 是 transient UI lease，不寫入 chat history；new chat、terminal turn 和 close
  都會清除，避免過期 action 在下一個 turn 可執行。
- runtime teardown 仍透過 Qt signal 與 event loop 收斂；focused gate 量測
  `AgentManager.close()` 返回 latency 與清理期間 GUI heartbeat，不以固定布林值宣稱 non-blocking。

### 5. Tools

`XBrainLab/llm/tools/definitions/` 定義工具名稱、參數 schema、描述和是否需要 confirmation。

`XBrainLab/llm/tools/real/` 是目前真的操作 app 的工具。

`XBrainLab/llm/action_contracts.py`是目前model-facing contract的唯一source；real、mock、debug與
prompt registry必須精確等於下列17個工具：

```text
import_eeg_data / select_channels / set_montage / create_epochs
configure_dataset_split / select_model / configure_training
apply_bandpass_filter / apply_notch_filter / resample_data / set_reference / normalize_data
start_training / stop_training / reset_preprocessing / clear_training_history
switch_panel
```

其中七個setup工具是零參數typed GUI completion；五個preprocess工具直接走ApplicationService；
四個lifecycle工具沿用backend capability/confirmation；`switch_panel`是唯一navigation。Retired
dataset protocol、recipe、query、standard-preprocess與analysis wrapper不在runtime registry，模型提出
未發布名稱會在adapter前fail closed。完整membership與參數契約由
[Agent target intent ledger](../target/agent.md#target-intent-ledger)擁有。

目前real tools有兩條路徑：

```text
Mapped workflow tool
  |
  v
execute_application_tool_command(...)
  |
  v
ApplicationService.execute(...)
  |
  v
ToolCommandResult.from_command_result(...)

GUI completion / navigation tool
  |
  v
typed UiRequest + correlated UI host
  |
  v
existing dialog / panel owner
  |
  v
ApplicationService / MainWindow terminal
```

這表示 assistant 目前不是自己複製一套 backend，而是透過 ApplicationService 進入既有
`Study` 狀態。2026-05-12 physical removal slice 後，product runtime real tools 和
compatibility implementations 都不能使用 `BackendFacade`；mapped workflow tools 以 command
result / command query 為準。

`XBrainLab/llm/tools/application_surface.py`是agent tool與ApplicationService command的對映層；
`ContextAssembler`依backend stage發布static target schemas，`ToolAttemptCoordinator`與
`ToolExecutionCoordinator`在execution前重讀同generation publication、schema、capability與
confirmation。

`ToolCommandResult` 是目前 agent-facing typed result adapter：

- ApplicationService blocked command 會回傳 structured failed result，包含 `command_name`、
  `blocked_reason`、capability 和 state snapshot。
- 五個direct preprocess與四個lifecycle tool把`CommandResult`直接轉成`ToolCommandResult`；
  adapter不保存第二份workflow state或confirmation policy。
- 七個GUI completion tool共用一個thin handoff adapter；trusted action contract固定route與decision
  fields，模型參數永遠是`{}`。只有dialog的completed/cancelled/blocked/unavailable/failed outcome
  能結束turn。
- `switch_panel`等待MainWindow/subview materialization callback，不把UiRequest emission當成功。
- Data Interpretation、analysis與query services仍供產品GUI/backend使用，但沒有Assistant wrapper。
- 缺少direct tool必要參數時，strict model branch使用`respond_to_user`；adapter不套default、不走
  legacy fallback。
- `CommandResult` 可直接轉成 agent payload；conversation history 中的 `Tool Output` 已保留
  `ok`、`tool_name`、`command_name`、
  `message`、`error_type`、`recoverable`、`state`、`capability`、`diagnostics`、
  `raw_result` JSON payload。
- `set_montage`走既有Montage Settings UI；Cancel不產生montage mutation。Evaluation、Visualization
  與Saliency由`switch_panel`導向既有panel，不以Assistant tool重建readiness或render owner。

## Workflow State Gate

`XBrainLab/llm/pipeline_state.py` 會把 real `Study` 的 workflow stage 導向
`ApplicationService.get_state().pipeline_stage`，讓 prompt narrative、capability policy
和 command execution 共用 backend snapshot truth。mock / legacy non-product callers 才保留
direct Study-shaped reads；真正可用工具與 blocked reason 仍由 ApplicationService capability
policy 產生。

`ContextAssembler`以backend `pipeline_stage`選擇`STAGE_CONFIG`中的approved target schemas；這是prompt
publication。ApplicationService capability不是另一個prompt router，而是在proposal後再次做authoritative
admission。若state publication不可靠，prompt stage固定為`unavailable`且只保留`switch_panel`與
`respond_to_user`。

RAG examples也受同一條17-tool與stage publication邊界約束：
`RAGIndexer`、`BM25Index` 和 `RAGRetriever` 會透過
`XBrainLab/llm/rag/example_policy.py` 排除所有未發布 tool examples，包括舊 dataset-info、direct
load / attach 與 granular preprocess names。這同時處理新建 index 和使用者機器上已存在的舊 Qdrant
collection，避免 legacy few-shot examples 被重新注入 local LLM prompt。

目前stage包括：

- `empty`
- `data_loaded`
- `preprocessed`
- `epoch_ready`
- `dataset_ready`
- `training`
- `trained`

Stage決定模型看見的候選集合；ApplicationService capability仍決定proposal是否能執行。匯入後的
working copy本身不代表已preprocess：`preprocessed.operations`為空時stage是`data_loaded`；Channel或任一
direct preprocess成功後才是`preprocessed`。Epoch後進入`epoch_ready`，split、model與training
settings全部完成後才是`dataset_ready`。

## 目前可信判斷

已對照 source code 的部分：

- chat UI、agent manager、controller、worker、engine、tool registry 都存在。
- registry精確發布17個approved target tools；retired wrappers在adapter前fail closed。
- direct tools進`ApplicationService.execute(...)`；GUI tools進既有correlated handoff owner。
- `LLMController`會做strict parser、stage/publication verification、capability、confirmation與單一tool
  turn limit，不做Host intent narrowing或continuation。
- `pipeline_state.py`使用ApplicationService publication的workflow stage。
- runtime backend selection 已由 structured config 管理，不應再用 UI label 判斷。

已在本輪 runtime 驗證的部分：

- local model catalog、download preflight 和 health-check script 存在。
- closure-worktree runtime inspection 回報 Granite 3.3 2B `gpu-ready`，其 path-scoped cache 約
  `5.07 GB / 20 GB`；root launcher cache 的 `12.77 GB` 不是同一個 checkout。
- frozen Granite 34個positive selection cases曾在先前exact source通過；本candidate擴為48 cases後必須
  在最終exact source重跑，舊34-case結果不能代替。
- local runtime unavailable 時，chat panel 會保持可開並顯示原因；first-run consent 只在
  local backend 還未 acknowledged 且即將啟用時出現。
- no-model diagnostic runtime可走真ChatPanel、MainWindow、ApplicationService與tool correlation，
  但manifest/automated test不等於三份真人walkthrough已完成。
- product-flow tests 覆蓋 normal chat response、empty response、worker error、local unavailable、
  blocked command feedback、assistant click-through layout。

尚未在本輪完整驗證的部分：

- RAG corpus 的品質和可用性。
- 長時間、多步 tool-call loop 在真實使用者 workflow 中是否穩定。
- agent 操作完整資料 pipeline 的端到端正確性。
- 真 Windows launcher / human desktop acceptance。
- 長時間真人桌面 session、跨重啟 cache lifecycle 與 frozen Granite benchmark。
- 最終48-case Granite gate、真model safe E2E與三份真人frontend walkthrough尚未在同一candidate
  source閉合。
- Windows native layout、dialog interaction與完整PhysioNet CPU workflow仍需要使用者手測。

Historical Phi evaluation artifacts are not current product or thesis evidence. Superseded raw、
host-assisted或`121/121` reports不得作為current Granite accuracy。只有同一candidate source的
48-case strict report可支撐本輪bounded selection claim，且仍不等於tool execution或產品ready。

## 架構評斷

目前設計是「可工作的中間狀態」。

好的地方：

- UI thread 和 LLM generation 已經分開。
- assistant 有 workflow stage awareness。
- real tools 沒有繞過 backend，而是經過 ApplicationService command / query result。
- mapped workflow tools 已可直接用 ApplicationService command result，不必只解析 legacy 字串。
- Data Interpretation 的 backend lifecycle 已從 `ApplicationService` 拆到 focused service，
  agent tool surface 不需要知道該 internal boundary，只依賴同一份 command result / state snapshot。
- destructive / long-running 操作有 confirmation 機制。
- runtime 已開始用 structured config 管理，而不是靠 UI label 判斷。

主要問題 / 明確邊界：

- local-only runtime 已是 product path；remote runtime 若日後作歷史 fixture，必須保持 optional 且
  product code 不 import。
- `BackendFacade` 已移除；若重新加入 wrapper，agent 會回到分裂 workflow truth。
- 舊 UI request 相容路徑仍有字串協定；新 workflow handoff / interaction outcome 已有 typed
  contract，但不能宣稱所有 UI side effect 都完成 typed migration。
- `CommandParser`驗證模型產生的strict JSON text envelope；它不是host-native structured tool calling，
  但不掃描prose或接受wrapper。
- strict envelope、publication/stage verification、capability與confirmation守住目前product
  contract；模型selection仍必須由48-case gate與真人safe E2E驗證。
- `AgentManager` 已抽出 presentation、runtime lifecycle、workflow handoff 與 montage coordinator，
  但仍是偏大的 Qt orchestrator，後續應按責任切片而不是新增 fallback。
- RAG 已接入 controller，但本輪尚未驗證資料來源和品質。
- Confirmation risk 仍以 `destructive` 布林值和文字種類描述，尚未成為 setting change、costly
  operation、irreversible action 等 typed semantic policy。

## Approved target reference

Stable v2的tool membership、backend-owned stage、strict envelope、thin Host、GUI terminal、diagnostic
walkthrough與candidate gates只由[Agent target](../target/agent.md)定義。Current source已完成17-tool
cutover與obsolete wrapper removal；candidate仍缺同source 48-case、完整handoff與真人acceptance，
因此不能宣稱Assistant-ready。

## 文件狀態

這份文件目前是 `verified engineering checkpoint`。

它已對照主要source code、17-tool boundary與no-model diagnostic contract；仍沒有證明最終48-case、
長時間真人workflow、Windows acceptance或thesis-grade accuracy。

local-only runtime cleanup 已對齊 product source：remote backend modules、remote key handling、
model settings remote UI 和 product remote switch path 已移除；剩餘驗證重點是長時間 local model
UI walkthrough、RAG 品質和真實多步 workflow。
