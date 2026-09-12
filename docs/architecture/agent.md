# Agent 目前架構

最後更新：`2026-09-12`

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
| `XBrainLab/ui/chat/` | chat panel、使用者輸入與 local runtime setup／model UI。 |
| `XBrainLab/ui/components/agent_manager.py` | UI 和 assistant 的 composition/presentation adapter；組合窄 lifecycle、dispatcher、publication 與既有 UI handoff owners。 |
| `XBrainLab/ui/components/assistant_command_dispatcher.py` | assistant controller thread ownership、queued shutdown、timeout retry 與 lifecycle cleanup。 |
| `XBrainLab/ui/components/assistant_runtime_lifecycle.py` | local runtime activation、terminal close、recoverable error 與 immutable runtime state。 |
| `XBrainLab/ui/components/assistant_application_publication_coordinator.py` | 將 revisioned application publication 與 training terminal notice 投影到 Assistant。 |
| `XBrainLab/llm/agent/controller.py` | 組合 agent turn：context、parser、verification、confirmation 與 bounded tool execution；不再保存 writable lifecycle aliases。 |
| `XBrainLab/llm/agent/turn_orchestrator.py` | `AssistantTurnOrchestrator` 擁有 host/RAG/generation/cancellation correlation；`AssistantToolAttemptSession` 擁有 request-scoped counters 與 visible feedback。 |
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
- 發出停止生成與模型設定等 signal。
- 顯示 local runtime 狀態；model menu 不再提供 Gemini/API 產品選項。
- debug 模式下可觸發測試用 tool command。

它不應該直接懂 backend workflow。

### 2. AgentManager

`AgentManager` 是 UI 和 agent runtime 的 composition/presentation adapter。

它負責：

- 透過 runtime lifecycle 與 command dispatcher 建立、啟動及關閉 `LLMController`，而不是直接擁有 worker process 細節。
- 將 chat panel 的 typed turn 交給 dispatcher，並將 assistant presentation、activity 與錯誤狀態送回 UI。
- 透過既有 UI handoff host 處理 switch panel、montage、設定與 confirmation，不在 chat 裡建立第二套 workflow form。
- 由 runtime lifecycle 將選定模型解析為 immutable `AssistantRuntimeLaunchSpec`，不以 UI label 判斷 runtime identity。
- 以 `ApplicationViewPublication.revision` 確認 GUI 已套用哪一份 backend state；只有 matching
  revision acknowledgement 後，才接收該 publication 保留的 terminal lifecycle event。

UI side effect 仍由 structured tool result 的 UI request 交給 `AgentManager`，但會沿用既有 dialog；
request 打開後 workflow 會停止並顯示 waiting state，不會繼續猜測使用者選擇。

### 3. LLMController

`LLMController` 是 agent turn 的組合層；mutable lifecycle 已有明確 owner。

工具 handoff 的名稱／command／decision fields 驗證與 request 建構由既有 `ui_handoff` 模組
依 canonical registry 完成；controller 只發送有效的 typed request。`ToolAttemptCoordinator`
由自己的 decision/context 建立 confirmation risk、參數與 publication generation；
`ConversationHistory` 選出排除 host feedback 的最近 human request。RAG result 的
cancelled／turn-id／waiting 接受條件由 `AssistantTurnOrchestrator` 決定，controller 仍保留
Qt processing／closing admission。這些內部責任移交不新增工具或改變 confirmation policy。

它負責：

- 建立 `ToolRegistry` 並註冊 real tools。
- 組prompt：strict policy、stage-published target schemas、minimal state card、bounded RAG、最新user與
  最多上一則Assistant-visible訊息。
- 讓 `AgentWorker` 在 background thread 生成回覆。
- 用`CommandParser`只接受exact三欄JSON envelope；不做寬鬆抽取或legacy fallback。
- 用 `VerificationLayer` 檢查 registered tool schema、required parameter、JSON-like type、
  enum、confidence 和部分資料範圍；五個direct preprocess另由同一verification boundary驗證required
  value確實來自latest user request，無法驗證時回一般Assistant追問且不進executor。
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
retry、tool failure/execution 與 visible response 只在
`AssistantToolAttemptSession`。Architecture gate 會以 AST 同時掃 production controller 與測試
fixture，避免測試寫入無效 instance attribute 後產生假通過。

`ToolExecutionCoordinator` 只接收 study、registry、metrics 與三個 lifecycle/status callbacks，
不持有整個 Controller；它在既有 execution module 綁定 reviewed publication generation。
Controller 保留 missing-generation 拒絕與 Qt delivery。有效 proposal 只執行一次、等待互動或
結束回合；format retry 發生在有效 proposal 之前，因此舊 repeated-proposal history／loop-break
分支已移除，不影響 strict-envelope retry 或 one-action admission。

Controller shutdown 只使用實際 `AgentWorker`／`QThread` 的 acknowledgement、timeout/retry 與
native-exit probe；不再提供專供非 QObject／QThread 測試替身使用的成功路徑。Worker 已釋放／
刪除、RAG cleanup 未完成與晚到的 Stop acknowledgement 仍由原有 lifecycle fence 處理。

UI 不可直接讀 `AgentWorker.engine` 或 generation thread。worker 只發出 model id、backend mode
與 initialized 狀態的 snapshot；`AgentManager`、VRAM conflict check 和 model deletion preflight
都讀 `LLMController.runtime_snapshot()`。architecture guard 會阻擋 UI 回到 worker internals。

這一層目前同時包含 agent orchestration 和一部分 workflow policy。所有 mapped workflow
command 仍由同一個 Study-scoped ApplicationService lock 序列化，避免 UI 與 assistant 同時 mutation。

### Prompt state projection

目前prompt不使用Host intent narrowing、recommended-next-step或deterministic continuation。
Assistant 已移除曾經重複保存這些資訊的 `decision_context`／turn-authorization shadow；
`ContextAssembler`從同一份immutable `ApplicationViewPublication`投影backend-owned stage與最小state
card，再依`STAGE_CONFIG`發布該stage的approved target schemas。模型只在這個集合中選一個tool，
或使用`respond_to_user`；Host不替模型選前置步驟或自動接續下一個mutation。

Prompt history只保留最新user訊息與最多一則Assistant-visible訊息，並排除`Tool Output:`、structured
envelope與內部system payload。bundled gold set目前有23個英文examples，維持18個approved tools的
coverage；RAG example也只能在同一stage的approved tool集合中檢索，不能授予capability、confirmation
或continuation權限。目前retriever仍以semantic ranking取`TOP_K = 3`；target所述canonical／top-2
selection尚未實作，不能把兩者混為同一policy。

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

模型選擇與 exact revision 由[有效決策](../decisions/README.md)及 immutable catalog 擁有：
Granite 4.0 Micro 3B 是 primary，Granite 3.3 2B 是明確的 lower-memory selection；任一選定模型
不可用時不 silent fallback。磁碟上存在其他模型不代表 product support，Settings 只發布支援清單。

`platform_paths` 擁有 per-user config 與 model cache 路徑；`LLMConfig` 預設使用該 owner，
不是每個 checkout 自帶一份模型。Windows 預設設定為 `%APPDATA%\XBrainLab\settings.json`、
模型 cache 為 `%LOCALAPPDATA%\XBrainLab\models`。`XBRAINLAB_CONFIG_DIR` 與
`XBRAINLAB_MODEL_CACHE_DIR` 可分別覆寫；catalog 在選定 cache 下驗證 pinned snapshot 與容量。
舊 repo-root 設定只用於既有一次性匯入，不是正常寫入位置。環境操作方式見
[本機環境](../developer/local-setup.md)。

WSL launcher 有自己的部署路徑選擇：若存在舊 Granite cache 就沿用，否則選 repo 所在 Windows
磁碟的 `XBrainLabCache/models`，RAG 使用 `XBrainLabCache/rag`；也支援其明定的 cache-root override。
這不是 Windows native bootstrap 或一般 Python 啟動的預設路徑，不新增 model selection／quota owner。

Cache 大小與 runtime 量測是 path/source-scoped evidence，不能由架構文件證明目前機器已安裝哪些
模型。引用量測時仍需記錄 cache path、full SHA、dirty state 與 model revision；歷史數值從 Git／
原始 evidence 追溯，不作為目前 runtime 狀態。

Runtime policy：

- `XBrainLab/llm/core/model_catalog.py` 是 local model allow-list / block-list / size policy 的單一來源。
- 下載前必須通過 `plan_model_download()`，限制單模型 10GB、總 cache 20GB。
- `AgentManager` 首次啟用 local runtime 時只在 Assistant Dock 顯示 inline setup：exact selected model
  label、estimated VRAM、cached model的`Enable Assistant`，或missing cache的`Set up model`與唯一
  `Assistant Settings`入口；不再建立first-run modal，app startup也不會自動載入大型local model。
- runtime resolver 只啟動設定中明確選定且可用的 exact model；若不可用就回 typed unavailable，
  不靜默改用另一個 catalog model。
- `LocalBackend` 會阻擋未列入 product catalog 或被中國模型 policy 擋下的 repo id。
- `LocalBackend` 的 `trust_remote_code`、CUDA dtype、system-role 與 runtime context budget 都來自
  immutable catalog spec；本機 settings 不能放寬 remote-code trust。
- `LLMConfig` 會把舊 `INFERENCE_MODE=api` 或 settings 裡的 Gemini/API mode 讀成 `local`。
- `LLMEngine` 只會 instantiate `LocalBackend`；product package 已移除 remote backend modules。
- `AgentWorker.reinitialize_agent(...)` 只接受 lifecycle 已解析的 `AssistantRuntimeLaunchSpec`；
  raw model name／generic alias 會 fail closed，不會改用 remote backend。
- `ModelSettingsDialog` 只保留 local model install/delete/activate 和 generation parameters，不再有
  remote key verification UI。
- `tests/architecture_compliance.py` 會靜態掃描 product path，禁止 remote backend class / key env path
  回到 `XBrainLab/`。

目前仍要保留在架構判讀中的 runtime 行為包括：

- runtime config reload。
- model / backend switch。
- generation timeout。

`LLMConfig` 和 `AssistantRuntimeSelection` 是 runtime truth。UI 顯示文字不能當成真實 backend 狀態。

Assistant 的已接受 bounded baseline 與 promotion 限制由[目前狀態](../current.md)及
[有效決策](../decisions/README.md)擁有；本頁不複製歷史分數或推論目前 cache 狀態。
Host receipt／format recovery 不等於模型自主正確，也不取代真人 workflow 或 thesis evidence。
4-bit loading 仍是 optional path；`accelerate` / `bitsandbytes` 不是預設產品啟動硬需求。

Gemini/API 不再列為產品驗證目標；default dependencies 不包含 remote SDK。若歷史研究需要遠端
fixture，必須放在明確 optional legacy path，不能被 product code import。

### Response and presentation boundary

普通回覆、空回覆、worker failure、blocked action 與 successful tool 都必須有 typed visible
terminal；diagnostic detail 不洩漏到 transcript。Confirmation card 保留 exact request identity，
不從顯示文字重建參數；Stop／New Chat／Close 不得沿用過期批准。
Workflow panels 只 render revisioned `ApplicationViewPublication`，command-result signal 只管理
Assistant activity／terminal ownership，不以 `changed_state` 另建 repaint 路徑。
Chat 的 widget、scroll、輸入與 inline setup 契約見[UI 架構](ui.md#chat-product-contract)；
真模型、native capture 與人工驗收要求見[驗證契約](../validation/README.md)。

### 5. Tools

`XBrainLab/llm/tools/definitions/` 定義工具名稱、參數 schema、描述和是否需要 confirmation。

`XBrainLab/llm/tools/real/` 是目前真的操作 app 的工具。

`XBrainLab/llm/action_contracts.py`是目前model-facing contract的唯一source；product、debug、evaluator與
prompt 共用同一份工具定義，registry必須精確等於下列18個工具。模擬工具與其獨立 workflow state
已移除；evaluator沿用既有controller harness的執行阻擋，不呼叫工具：

```text
import_eeg_data / select_channels / set_montage / create_epochs
configure_dataset_split / select_model / configure_training
apply_bandpass_filter / apply_notch_filter / resample_data / set_reference / normalize_data
start_training / stop_training / reset_preprocessing / clear_training_history
switch_panel / compute_saliency
```

其中七個setup工具是零參數typed GUI completion；五個preprocess工具直接走ApplicationService；
四個lifecycle工具沿用backend capability/confirmation；`switch_panel`是唯一navigation；
`compute_saliency`在trained stage先走Assistant confirmation，再以零參數UI action沿用目前
Visualization panel選定的run、method、resource confirmation與operation publication。Retired
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
- `compute_saliency`不讓模型填run/method/settings；它等待相同operation的completed/cancelled/failed
  terminal，不把command schedule receipt當成功。
- Data Interpretation、analysis與query services仍供產品GUI/backend使用，但沒有Assistant wrapper。
- 缺少direct tool必要參數時，strict model branch使用`respond_to_user`；adapter不套default、不走
  legacy fallback。
- `CommandResult` 可直接轉成 agent payload；conversation history 中的 `Tool Output` 已保留
  `ok`、`tool_name`、`command_name`、
  `message`、`error_type`、`recoverable`、`state`、`capability`、`diagnostics`、
  `raw_result` JSON payload。
- `set_montage`保留既有 public tool identifier，但 handoff 走 Dataset panel 的 `Electrode Layout`
  entry；Cancel不產生 montage mutation。Evaluation與Visualization 由`switch_panel`導向既有panel；
  Compute Saliency只觸發既有panel action，不重建readiness或render owner。

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

RAG examples也受同一條18-tool與stage publication邊界約束：
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

## Evidence and architectural limits

Source／focused tests 支持 strict parser、published action admission、Command spine、correlated
confirmation／handoff 與 owned runtime cleanup 的 bounded contract，不直接證明任意模型回答、
RAG 語意品質、所有資料流程或 Windows 真人操作。每次 candidate 的成功與限制應依
[驗證契約](../validation/README.md)判定；舊 source 的 artifact 不能當作新 source 的通過。

仍需保留的架構限制：

- `LLMController` 與 `AgentManager` 仍是偏大的 composition／callback 集中點。後續抽取必須
  對應既有責任與真實 callers；不能只搬移行數或新增另一個控制層。
- Strict JSON envelope 是模型生成文字的驗證邊界，不是模型自主語意正確的保證。
- RAG process ownership 與安全 admission 不證明 corpus／retrieval 的科學或語意品質。

## Approved target reference

Stable v2的tool membership、backend-owned stage、strict envelope、thin Host、GUI terminal、diagnostic
walkthrough與candidate gates只由[Agent target](../target/agent.md)定義。Current source已完成18-tool
cutover與obsolete wrapper removal；3B primary／2B lower-memory catalog仍只是bounded Local Assistant
checkpoint，不把任一固定模型或deterministic host guards宣稱為安全零容忍或語意正確性保證。

## 文件狀態

本頁描述 current source boundary；產品版本與已接受能力以[目前狀態](../current.md)為準。
不在架構文件保存當次 cache、runtime 量測或 candidate 完成狀態。
