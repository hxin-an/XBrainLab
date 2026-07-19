# Agent 目前架構

最後更新：`2026-07-15`

## 範圍

這份文件描述 XBrainLab 內建 assistant 的目前架構與重構方向。

這裡的 agent 指 app 內的 workflow-aware software operation agent，不是外部開發用的 Codex。

## 一句話

目前 assistant 不是單純聊天視窗，而是已經能透過 tool call 操作 XBrainLab workflow 的功能層。

目前實際路徑是：

```text
ChatPanel
  |
  v
AgentManager
  |
  v
AssistantCommandDispatcher / AssistantCommandThread
  |
  v
LLMController
  |
  +--> AgentWorker / LLMEngine
  |
  +--> Parser / VerificationLayer / ToolRegistry
  |
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
  +--> Study-scoped reentrant command/state lock
  |
  v
Study / cached controllers
```

這是一個可工作的中間狀態，但還不是最終理想架構。

## 主要位置

| 區域 | 目前責任 |
| --- | --- |
| `XBrainLab/ui/chat/` | chat panel、使用者輸入、模型 / 執行模式 UI。 |
| `XBrainLab/ui/components/agent_manager.py` | UI 和 assistant 的接線層，負責啟動 controller、轉送訊息、處理既有 UI request、command refresh suppression。 |
| `XBrainLab/ui/components/assistant_command_dispatcher.py` | assistant controller thread ownership、queued shutdown、timeout retry 與 lifecycle cleanup。 |
| `XBrainLab/llm/agent/controller.py` | agent orchestration：context、parser、verification、confirmation 與 bounded tool loop。 |
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

`AgentManager` 是目前 UI 和 agent runtime 的整合點。

它負責：

- 在 `start_system()` 時建立 `LLMController(self.study)`。
- 將 chat panel 的輸入轉給 `LLMController.handle_user_input()`。
- 將 assistant 回覆、streaming chunk、錯誤狀態送回 UI。
- 處理需要 UI 介入的 request，例如 switch panel、confirm montage、confirm action。
- 透過 `LLMConfig.normalize_backend_mode()` 把 UI label 對齊 runtime key。

UI side effect 仍由 structured tool result 的 UI request 交給 `AgentManager`，但會沿用既有 dialog；
request 打開後 workflow 會停止並顯示 waiting state，不會繼續猜測使用者選擇。

### 3. LLMController

`LLMController` 是目前 agent 行為的核心。

它負責：

- 建立 `ToolRegistry` 並註冊 real tools。
- 組 prompt：conversation history、workflow state、RAG examples、ApplicationService policy 可用工具與 blocked reason。
- 讓 `AgentWorker` 在 background thread 生成回覆。
- 用 `CommandParser` 從 LLM 文字輸出中找 tool call JSON。
- 用 `VerificationLayer` 檢查 registered tool schema、required parameter、JSON-like type、
  enum、confidence 和部分資料範圍。
- 套用 ApplicationService capability gate，避免 assistant 在錯誤 backend state 呼叫不該開放的工具。
- 將已驗證的單一 tool 交給 `ToolExecutionCoordinator`；mapped workflow tool 透過
  `execute_application_tool_command(...)` 執行 ApplicationService command，直接取得
  `CommandResult` payload。
- tool command 開始時通知 `AgentManager` 抑制 observer duplicate refresh；完成後使用
  serialized `changed_state` 走 UI 共用 refresh coordinator，再重讀 ApplicationService state /
  capability snapshot。
- 處理 destructive / long-running tool 的 human confirmation。
- 防止明顯 tool loop，並限制 multi-step execution 次數。

UI 不可直接讀 `AgentWorker.engine` 或 generation thread。worker 只發出 model id、backend mode
與 initialized 狀態的 snapshot；`AgentManager`、VRAM conflict check 和 model deletion preflight
都讀 `LLMController.runtime_snapshot()`。architecture guard 會阻擋 UI 回到 worker internals。

這一層目前同時包含 agent orchestration 和一部分 workflow policy。所有 mapped workflow
command 仍由同一個 Study-scoped ApplicationService lock 序列化，避免 UI 與 assistant 同時 mutation。

### 執行模式

- `One Step`：每次只執行一個已通過 schema、verification、capability 與 confirmation policy 的步驟。
- `Workflow`：可連續執行安全步驟，直到 backend 回報 confirmation、`decision_needed`、
  `can_auto_execute=False`、`stop_after_success=True`，或需要開啟既有 UI dialog。Evaluate
  是 read-only terminal step，成功後停止，不會因 state 未改變而重複執行。
- descriptive `decision_boundary` metadata 本身不是停止條件；真正的 backend policy 和當前 state
  才決定能否繼續，避免每個 tool 都被靜態描述過早截斷。
- `recommended_next_step` 只由 `WorkflowDecisionContext` 產生；AgentManager 不再維護另一份推測。

### Workflow Decision Context

2026-05-31 bounded Copilot slice 後，LLM prompt 不再把長 conversation history 當成
workflow truth。`ContextAssembler` 會先從 `ApplicationService.get_state()` 和
`get_capabilities()` 產生一份 compact `WorkflowDecisionContext`，再把它放進 system prompt。

目前 decision context 會明確列出：

- `mode`：`step_by_step` 或 `continue_until_decision`。
- `workflow_stage`：使用者可理解的目前階段。
- `recommended_next_step` / `recommended_label`：下一個建議 backend command。
- `decision_needed`：缺哪些使用者決定，例如資料來源、epoch window、split strategy、model。
- `existing_ui_surface`：若需要人決定，應打開既有 Data Import wizard、Epoch dialog、
  Dataset split dialog、Training settings 或 Saliency settings，而不是在 chat 裡重做第二套 UI。
- `can_auto_continue` / `stop_reason`：是否可以繼續自動執行，以及為什麼必須停。
- `evidence` / `blocked_reasons`：從 backend state / capability policy 來的可追溯理由。

conversation history 仍保留作語境，但送進 LLM 的 history 只保留最近少量 user-visible
turns，並過濾 `Tool Output:`、`Request:` 和內部 system payload。這避免舊 tool result
或長聊天紀錄覆蓋目前 backend state。

Data Import lifecycle 也是 decision context 的一級狀態：

```text
source selected -> scan_source
scan ready      -> preview_interpretation
candidate ready -> validate_interpretation
validated       -> apply_interpretation boundary
applied         -> loaded raw data / preprocess
```

這讓 agent 在使用者說「繼續」時從目前 import recipe / candidate 狀態前進，而不是因為
聊天裡曾經提過資料夾就重複 scan。

### 4. Worker / Engine / Backend

`AgentWorker` 和 `LLMEngine` 負責 LLM runtime。

目前產品 runtime 是 local-only assistant：

- local model backend。
- 不依賴 API key。
- 不把 Gemini/API 當成產品 execution mode。
- 優先讓本地模型、模型 cache、GPU/CPU fallback 可理解、可測、可交接。
- 模型選型不使用中國公司或中國來源模型。
- Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 等模型不列入 primary / fallback 選型。
- 優先考慮非中國來源、授權清楚、可本地部署的模型。

2026-07-15 local runtime truth：

| role | model | provider | estimated download | cache status | smoke |
| --- | --- | --- | ---: | --- | --- |
| primary | `microsoft/Phi-4-mini-instruct` | Microsoft | 7.69 GB | cached | real GPU ChatPanel workflow PASS |
| fallback | `microsoft/Phi-3.5-mini-instruct` | Microsoft | 7.64 GB | cached | cache/preflight present; no current full ChatPanel run |

cache 位置：

```text
XBrainLab/llm/core/models
```

`scripts/dev/inspect_local_assistant_runtime.py --format markdown` reports
`classification: gpu-ready`, `has_local_cache: True`, and cache usage `15.34 GB` against the
20 GB product limit. The active model is Phi-4 mini. The real ChatPanel artifact covers one
state-query tool turn and one normal answer turn; it is not a long-session or fallback-model claim.
舊 Qwen cache 已刪除，catalog / architecture guards 會阻止被禁用來源重新進入 product path。

新增 runtime policy：

- `XBrainLab/llm/core/model_catalog.py` 是 local model allow-list / block-list / size policy 的單一來源。
- 下載前必須通過 `plan_model_download()`，限制單模型 10GB、總 cache 20GB。
- `AgentManager` first-run consent 會在首次啟用 local runtime 前顯示 GPU/CPU resource
  notice、download estimate、cache status，並提供 Enable / Download / Use existing cache /
  Later / Disable；app startup 不會自動載入大型 local model。
- `AgentWorker` 啟動 local runtime 時會先嘗試設定中的 local model；若不可用且 fallback cache 可用，
  會依 policy 切到 fallback model，而不是啟動 API / Gemini。
- `LocalBackend` 會阻擋未列入 product catalog 或被中國模型 policy 擋下的 repo id。
- Phi remote-code compatibility patch 目前只針對 runtime annotation / cache API 差異，並用
  prompt smoke 與 structured-output smoke 驗證。
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

目前 primary / fallback cache 都存在，且 primary GPU ChatPanel workflow 已通過。新的 unassisted
raw candidate score 是 `6/12`；host-assisted product policy score 是 `12/12`，因為 host 會執行
request admission、normalization、verification 和 capability blocking。後者不能替代 raw-model
accuracy，也不能把歷史 `117/117` 或 `121/121` artifact 恢復成 thesis claim。兩種分數都不能
替代長時間 ChatPanel workflow、Windows launcher、UI usability 或 human desktop acceptance。
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

- `hello` / `hi` 等 greeting 先回產品友善導引，不急著呼叫 `list_files` 或其他工具。
- empty response 會發出 visible error，並讓 UI 回 idle。
- tool-only successful turn 會產生 user-facing visible summary。
- ApplicationService blocked command 會立即發出 shared blocked reason，但 transcript 不顯示
  raw tool name、backend command name 或 snake_case command。
- `list_files` missing directory 會追問 folder/path；empty directory 會顯示空狀態文字，
  不會把 `Error: directory is required` 或 `[]` 當 assistant 回覆。
- tool error 會分成 input / precondition / runtime 等 product-level bucket；developer detail
  只留在 structured history / diagnostics / logs。
- busy re-entry 不會默默吃掉使用者輸入；UI 會提示 assistant still processing。
- tests 必須覆蓋 normal response、empty response、worker error、local unavailable first-open、
  missing argument、empty tool result、state-gated command、successful command summary。

### 5. Tools

`XBrainLab/llm/tools/definitions/` 定義工具名稱、參數 schema、描述和是否需要 confirmation。

`XBrainLab/llm/tools/real/` 是目前真的操作 app 的工具。

目前 real tools 有兩條路徑：

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

UI-request / read-only tool
  |
  v
get_application_service(study)
  |
  v
ApplicationService / Command API
  |
  v
Study / DataManager / TrainingManager / controllers
```

這表示 assistant 目前不是自己複製一套 backend，而是透過 ApplicationService 進入既有
`Study` 狀態。2026-05-12 physical removal slice 後，product runtime real tools 和
compatibility implementations 都不能使用 `BackendFacade`；mapped workflow tools 以 command
result / command query 為準。

新增 `XBrainLab/llm/tools/application_surface.py` 作為 agent tool name 和
ApplicationService command name 的對映層。`ContextAssembler` 用它決定可列出的 tools；
`LLMController` 在 tool execution 前再次用它檢查 blocked reason。

`ToolCommandResult` 是目前 agent-facing typed result adapter：

- ApplicationService blocked command 會回傳 structured failed result，包含 `command_name`、
  `blocked_reason`、capability 和 state snapshot。
- mapped workflow tools 會直接把 `CommandResult` 轉成 `ToolCommandResult`，目前包含
  Data Interpretation tools（`scan_source`、`preview_interpretation`、
  `validate_interpretation`、`apply_interpretation`、`save_interpretation_recipe`、
  `reload_interpretation_recipe`）、`load_data`、`attach_labels`、preprocess tools、
  `epoch_data`、`generate_dataset`、`set_model`、`configure_training`、`start_training`、
  `evaluate`、`visualize`、`saliency`、`clear_dataset`。
- Data Interpretation tools 仍只透過 `ApplicationService.execute()` 進入 backend；實際
  scan / preview / validate / apply / recipe lifecycle 已在 backend
  `DataInterpretationCommandService` 中，reviewed metadata / label carrier side effects 已在
  `DataInterpretationApplyService` 中，不在 agent controller 或 real tool 內重建
  第二套 state。
- Data Interpretation tools 與 analysis-readiness tools（`evaluate` / `visualize` /
  `saliency`）已註冊在 definitions / real / mock tool set；Context Assembler 可以把 backend
  capability policy 判定為 enabled 的新工具列入 prompt。
- `LLMController` 對 `apply_interpretation` 這類 dynamic decision boundary 不再只看 static
  `BaseTool.requires_confirmation`；若 backend capability 回報 `requires_confirmation` /
  `confirmation_required`，controller 會暫停並等待 UI confirmation，確認後才對
  `apply_interpretation`、`clear_dataset`、`start_training` 帶 `confirmed=True` 執行。
- real `Study` 下，mapped workflow tool 如果缺少必要參數而無法建立 ApplicationService
  command，`application_surface` 會回 typed input failure，要求使用者補資訊；它不再退回
  legacy real-tool execution。`set_montage` 仍是明確 UI confirmation request path，mock /
  legacy non-Study test path 仍可使用 legacy tool execution。
- compatibility real tools 若仍回傳 `"Error: ..."`、`"Failed ..."` 等字串，controller 會將它
  正規化成 failed result，不再把 compatibility failure 當成 successful tool execution。
- read-only `list_files` / `get_dataset_info` 現在也會正規化為 typed result；visible transcript
  透過 product formatter 顯示，不直接露出 Python list、schema error 或 tool syntax。
- `CommandResult` 可直接轉成 agent payload；conversation history 中的 `Tool Output` 已保留
  `ok`、`tool_name`、`command_name`、
  `message`、`error_type`、`recoverable`、`state`、`capability`、`diagnostics`、
  `raw_result` JSON payload。
- `set_montage` 仍走 UI confirmation request；`switch_panel` 仍是 UI routing request；
  `list_files` / `get_dataset_info` 仍是 read-only / inspection path。舊 `load_data` /
  `attach_labels` 保留為 compatibility surface，但不再是 Empty / Data Loaded /
  Preprocessed stage prompt 的 primary tool language；Goal 1 新資料入口主線以 Data
  Interpretation taxonomy 為主。

## Workflow State Gate

`XBrainLab/llm/pipeline_state.py` 會把 real `Study` 的 workflow stage 導向
`ApplicationService.get_state().pipeline_stage`，讓 prompt narrative、capability policy
和 command execution 共用 backend snapshot truth。mock / legacy non-product callers 才保留
direct Study-shaped reads；真正可用工具與 blocked reason 仍由 ApplicationService capability
policy 產生。

目前 `ContextAssembler` 以 ApplicationService capability policy 作 mapped workflow tool 的唯一
曝光真相；stage config 只提供敘事與少數非 command UI/inspection tool，不再當第二個 allowlist。
legacy compatibility tools 即使 backend compatibility capability 可用，也不會重新放回 primary
prompt。若 capability snapshot 讀取失敗，只保留不屬於 command policy 的安全 UI/inspection tool，
不退回 stage-based workflow exposure。

同日後續 RAG cleanup 把 bundled gold-set examples 也納入同一條邊界：
`RAGIndexer`、`BM25Index` 和 `RAGRetriever` 會透過
`XBrainLab/llm/rag/example_policy.py` 排除含 `load_data` / `attach_labels` /
`import_labels` 的 examples。這同時處理新建 index 和使用者機器上已存在的舊 Qdrant
collection，避免 legacy few-shot examples 被重新注入 local LLM prompt。

目前主要 stage 包括：

- `empty`
- `data_loaded`
- `preprocessed`
- `dataset_ready`
- `training`
- `trained`

舊 stage table 不再是 execution gate。這很重要，因為 stage table 比較像單一路徑
pipeline，不足以完整描述同一 dataset 上多個 training run、已完成 result 可視覺化、
以及 reset / new session / fork 這類高風險資料切換情境。

這不代表所有 tool 都能並行。沒有 loaded data 不能 preprocess，沒有 dataset 不能 training，沒有 trained result 不能 saliency / model-based visualization。epoch / dataset 形成後，load new data 應被擋下，除非使用者明確選擇 reset / new session / fork。

## 目前可信判斷

已對照 source code 的部分：

- chat UI、agent manager、controller、worker、engine、tool registry 都存在。
- real tools 目前會進 `get_application_service(study)` / `ApplicationService.execute(...)`。
- `LLMController` 會做 parser、verification、stage gate、confirmation、loop limit。
- `pipeline_state.py` 會從 live `Study` 推導 workflow stage。
- runtime backend selection 已由 structured config 管理，不應再用 UI label 判斷。

已在本輪 runtime 驗證的部分：

- local model catalog、download preflight 和 health-check script 存在。
- runtime inspection 回報 Phi-4 mini `gpu-ready`，兩個 approved model cache 共 `15.34 GB`。
- 真 ChatPanel workflow 已完成 state-query tool turn 和一般回答 turn，並正常回 idle / shutdown。
- local runtime unavailable 時，chat panel 會保持可開並顯示原因；first-run consent 只在
  local backend 還未 acknowledged 且即將啟用時出現。
- assistant product UI 已改成使用者語言：workflow stage、local model status、next steps 和
  execution mode 不再用 raw command names 或 developer labels 當第一層資訊；model /
  execution mode 轉到 Options 或底部低干擾 status。
- product-flow tests 覆蓋 normal chat response、empty response、worker error、local unavailable、
  blocked command feedback、assistant click-through layout。

尚未在本輪完整驗證的部分：

- RAG corpus 的品質和可用性。
- 長時間、多步 tool-call loop 在真實使用者 workflow 中是否穩定。
- agent 操作完整資料 pipeline 的端到端正確性。
- 真 Windows launcher / human desktop acceptance。
- fallback model 的完整 ChatPanel run、長時間真人桌面 session 與跨重啟 cache lifecycle。

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
- `CommandParser` 是從 LLM 文字中掃 JSON，不是 host-native structured tool calling。
- `VerificationLayer`、request admission 與 strict-envelope recovery 已能守住目前 product
  contracts；raw local model 在 candidate slice 仍只有 50%，所以模型判斷本身不是完成狀態。
- `AgentManager` 已抽出 presentation、runtime lifecycle、workflow handoff 與 montage coordinator，
  但仍是偏大的 Qt orchestrator，後續應按責任切片而不是新增 fallback。
- RAG 已接入 controller，但本輪尚未驗證資料來源和品質。

## 目標架構

未來重構目標是讓 UI、Agent、Script 共用同一套 app operation surface。

assistant runtime 目標是 local-only。這可以讓開發、部署、論文驗證和隱私邊界簡化：

- 不需要 API key 管理。
- 不需要雲端 provider fallback policy。
- tool-call 驗證只需要面對一套本地 runtime。
- offline / local lab machine 的行為比較容易固定。

目標形狀：

```text
UI actions
Assistant tools
Headless scripts
  |
  v
Application Service / Command API
  |
  v
Domain managers / Study state
  |
  v
Data / Training / Evaluation / Persistence
```

在這個目標裡：

- agent-specific 的部分只負責自然語言、RAG、tool selection、verification、confirmation。
- LLM runtime 只保留本地模型路線，不再把 API / Gemini 作為產品路線。
- 真正 app 操作應該落在 shared command layer。
- UI side effects 應該改成 typed events / typed requests，而不是 `Request:` 字串。
- assistant / script product path 應直接使用 ApplicationService / Command API；不再保留
  `BackendFacade` compatibility adapter。
- tool taxonomy 可以重設計，不需要被目前 `real/` 工具切法綁住。

## 文件狀態

這份文件目前是 `verified engineering checkpoint`。

它已對照主要 source code、真 Phi-4 ChatPanel workflow 與 candidate eval；仍沒有證明 RAG 品質、
長時間多步 tool-call workflow、fallback model UI session 或 thesis-grade raw accuracy。

local-only runtime cleanup 已對齊 product source：remote backend modules、remote key handling、
model settings remote UI 和 product remote switch path 已移除；剩餘驗證重點是長時間 local model
UI walkthrough、RAG 品質和真實多步 workflow。
