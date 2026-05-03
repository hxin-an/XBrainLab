# Agent Architecture

最後更新：`2026-05-02`

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
LLMController
  |
  +--> AgentWorker / LLMEngine
  |
  +--> Parser / VerificationLayer / ToolRegistry
  |
  v
Real Tools
  |
  +--> ApplicationService capability policy / direct command execution for mapped workflow tools
  |
  v
BackendFacade
  |
  v
ApplicationService / Command API
  |
  v
Study / cached controllers
```

這是一個可工作的中間狀態，但還不是最終理想架構。

## 主要位置

| 區域 | 目前責任 |
| --- | --- |
| `XBrainLab/ui/chat/` | chat panel、使用者輸入、模型 / 執行模式 UI。 |
| `XBrainLab/ui/components/agent_manager.py` | UI 和 assistant 的接線層，負責啟動 controller、轉送訊息、處理 UI side effects。 |
| `XBrainLab/llm/agent/controller.py` | agent 主控制器，負責 context、RAG、parser、verification、tool loop、ApplicationService capability gate。 |
| `XBrainLab/llm/agent/worker.py` | 背景 thread 中的 LLM 初始化、生成、timeout、model switch。 |
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

目前 UI side effect 是透過 tool 回傳 `Request:` 字串，再由 `AgentManager` 處理。這是現況，不是理想長期介面。

### 3. LLMController

`LLMController` 是目前 agent 行為的核心。

它負責：

- 建立 `ToolRegistry` 並註冊 real tools。
- 組 prompt：conversation history、workflow state、RAG examples、ApplicationService policy 可用工具與 blocked reason。
- 讓 `AgentWorker` 在 background thread 生成回覆。
- 用 `CommandParser` 從 LLM 文字輸出中找 tool call JSON。
- 用 `VerificationLayer` 檢查參數、confidence、部分資料範圍。
- 套用 ApplicationService capability gate，避免 assistant 在錯誤 backend state 呼叫不該開放的工具。
- 對 mapped workflow tools 優先透過 `execute_application_tool_command(...)` 執行
  ApplicationService command，直接取得 `CommandResult` payload。
- tool turn 完成後由 `AgentManager.refresh_backend_status()` 重新讀 ApplicationService state
  snapshot / capability policy，更新 assistant UI diagnostics。
- 處理 destructive / long-running tool 的 human confirmation。
- 防止明顯 tool loop，並限制 multi-step execution 次數。

這一層目前同時包含 agent orchestration 和一部分 workflow policy。

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

2026-05-02 product runtime baseline：

| role | model | provider | estimated download | cache status | smoke |
| --- | --- | --- | ---: | --- | --- |
| primary | `microsoft/Phi-4-mini-instruct` | Microsoft | 7.69 GB | downloaded | prompt + structured-output passed |
| fallback | `microsoft/Phi-3.5-mini-instruct` | Microsoft | 7.64 GB | downloaded | prompt + structured-output passed |

cache 位置：

```text
XBrainLab/llm/core/models
```

目前 cache 約 `15.34 GB`，低於 20GB 上限。舊 Qwen cache 已刪除。

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

目前 primary / fallback local LLM 已通過 GPU prompt smoke 和 structured-output smoke。
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

Legacy / UI-request / read-only tool
  |
  v
BackendFacade(study)
  |
  v
ApplicationService / Command API
  |
  v
Study / DataManager / TrainingManager / controllers
```

這表示 assistant 目前不是自己複製一套 backend，而是使用 ApplicationService / BackendFacade
進入既有 `Study` 狀態。2026-05-02 product delivery slice 後，mapped workflow tools
已可直接消費 `CommandResult`；legacy facade string path 不再是所有 tool 的唯一 execution
surface。

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
  `clear_dataset`。
- Data Interpretation tools 已註冊在 definitions / real / mock tool set；Context Assembler
  可以把 backend capability policy 判定為 enabled 的新工具列入 prompt。
- `LLMController` 對 `apply_interpretation` 這類 dynamic decision boundary 不再只看 static
  `BaseTool.requires_confirmation`；若 backend capability 回報 `requires_confirmation` /
  `confirmation_required`，controller 會暫停並等待 UI confirmation，確認後才帶
  `confirmed=True` 執行。
- legacy real tools 若仍回傳 `"Error: ..."`、`"Failed ..."` 等字串，controller 會將它
  正規化成 failed result，不再把 legacy failure 當成 successful tool execution。
- read-only `list_files` / `get_dataset_info` 現在也會正規化為 typed result；visible transcript
  透過 product formatter 顯示，不直接露出 Python list、schema error 或 tool syntax。
- `CommandResult` 可直接轉成 agent payload；目前仍有部分 real tools 先走 facade legacy method，
  但 conversation history 中的 `Tool Output` 已保留 `ok`、`tool_name`、`command_name`、
  `message`、`error_type`、`recoverable`、`state`、`capability`、`diagnostics`、
  `raw_result` JSON payload。
- `set_montage` 仍走 UI confirmation request；`switch_panel` 仍是 UI routing request；
  `list_files` / `get_dataset_info` 仍是 read-only / inspection path。舊 `load_data` /
  `attach_labels` 暫時保留為 compatibility surface，但 Goal 1 新資料入口主線應改以
  Data Interpretation taxonomy 為主。

## Workflow State Gate

`XBrainLab/llm/pipeline_state.py` 仍會從 live `Study` 推出目前 workflow stage，主要作為
prompt narrative；真正可用工具與 blocked reason 改由 ApplicationService capability
policy 產生。

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
- real tools 目前會進 `BackendFacade(study)`。
- `LLMController` 會做 parser、verification、stage gate、confirmation、loop limit。
- `pipeline_state.py` 會從 live `Study` 推導 workflow stage。
- runtime backend selection 已由 structured config 管理，不應再用 UI label 判斷。

已在本輪 runtime 驗證的部分：

- local LLM primary / fallback model cache 存在且低於容量上限。
- primary / fallback 都可在 CUDA 上載入並回覆最小 prompt。
- primary / fallback 都可照 prompt-protocol 輸出 `{"tool_name":"get_state","arguments":{}}`。
- local runtime unavailable 時，chat panel 會保持可開並顯示原因；first-run consent 只在
  local backend 還未 acknowledged 且即將啟用時出現。
- assistant product UI 已改成使用者語言：workflow stage、local model status、next steps 和
  execution mode 不再用 raw command names 或 developer labels 當第一層資訊；model /
  execution mode 轉到 Options 或底部低干擾 status。
- product-flow tests 覆蓋 normal chat response、empty response、worker error、local unavailable、
  blocked command feedback、assistant click-through layout。

尚未在本輪完整驗證的部分：

- RAG corpus 的品質和可用性。
- 多步 tool-call loop 在真實使用者 workflow 中是否穩定。
- agent 操作完整資料 pipeline 的端到端正確性。
- 真 Windows launcher / true local model UI chat walkthrough。
- local-only runtime cleanup 已完成 product path 封口；仍未做真 local model 長時間 UI chat walkthrough。

## 架構評斷

目前設計是「可工作的中間狀態」。

好的地方：

- UI thread 和 LLM generation 已經分開。
- assistant 有 workflow stage awareness。
- real tools 沒有完全繞過 backend，而是經過 `BackendFacade`。
- mapped workflow tools 已可直接用 ApplicationService command result，不必只解析 legacy 字串。
- destructive / long-running 操作有 confirmation 機制。
- runtime 已開始用 structured config 管理，而不是靠 UI label 判斷。

主要問題：

- local-only runtime 已是 product path；remote runtime 若日後作歷史 fixture，必須保持 optional 且
  product code 不 import。
- `BackendFacade` 目前仍接到 `Study` 和 controllers，不是未來理想的 Application Service / Command API。
- tool result 和 UI request 主要靠字串協定，型別邊界不夠清楚。
- `CommandParser` 是從 LLM 文字中掃 JSON，不是 host-native structured tool calling。
- `VerificationLayer` 已有基本檢查，但還不是完整的 tool contract validation。
- `AgentManager` 同時處理 UI wiring 和 agent request，長期會讓 UI side effect 難測。
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
- `BackendFacade` 可以保留為 assistant / script adapter，但不應成為另一套業務邏輯來源。
- tool taxonomy 可以重設計，不需要被目前 `real/` 工具切法綁住。

## 文件狀態

這份文件目前是 `partially-verified`。

它已經對照主要 source code，但還沒有證明 local LLM runtime、RAG 品質、真實多步 tool-call workflow 都可穩定運作。

local-only runtime cleanup 已對齊 product source：remote backend modules、remote key handling、
model settings remote UI 和 product remote switch path 已移除；剩餘驗證重點是長時間 local model
UI walkthrough、RAG 品質和真實多步 workflow。
