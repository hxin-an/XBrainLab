# Target Agent

最後更新：`2026-05-04`

這份文件定義 XBrainLab agent 的目標態。

## 角色

XBrainLab 的 assistant 是 app 內 EEG workflow operator。

它不是：

- 普通聊天插件。
- 外部 coding assistant。
- 只會描述 UI 的 help bot。

它應該能：

- 讀取目前 workflow state。
- 選擇合適工具。
- 呼叫 backend command。
- 解釋它做了什麼。
- 在錯誤或缺資料時回報可行下一步。

## Local-only runtime

產品 runtime 已是 local-only。

這代表：

- `LLMConfig`、`LLMEngine`、`AgentWorker` 不接受 Gemini / remote API 作為產品
  execution mode。
- remote backend modules 已從 product package 移除；舊 settings / env 若指向
  `api` / `gemini`，必須 migrate local 或 fail closed，不可 instantiate remote backend。
- `openai` / `google-genai` 不在 default dependencies；若歷史研究需要，只能放在 optional
  `legacy-remote-llm` dependency group / legacy fixture，不可由 product code import。
- local model cache、dependency、GPU / CPU fallback 要可檢查。
- model switch、stop generation、timeout、VRAM diagnostics 要可驗證。
- 真 local LLM 長時間 ChatPanel walkthrough 仍未完成，不能用 prompt smoke 取代。

## Tool-call validation

tool-call validation 不只看回答像不像，也不應停在人工讀幾個範例。

目標是建立一套可重跑的 agent tool-call scoring system，用固定 benchmark cases 評估 agent 在 XBrainLab workflow 中的操作準確率。

它應驗證：

- intent 是否映射到正確 command。
- tool selection 是否正確。
- command input / parameters 是否正確。
- 資料入口 intent 是否走 Data Interpretation flow，而不是直接套用舊 `load_data` /
  `attach_labels` 心智模型。
- command 是否真的執行。
- 執行後 state 是否正確變化。
- error 是否可分類、可回報、可恢復。
- 多步 workflow 是否能維持 state。

評分輸出至少應包含：

- overall tool-call accuracy。
- 分項 accuracy：intent、tool、parameters、state transition、error recovery。
- per-stage accuracy：data import、preprocess、dataset、training、evaluation、visualization。
- invalid call rate。
- unsafe / blocked call rate。
- self-correction success rate。
- case-level failure taxonomy。

benchmark cases 應包含：

- single-turn workflow command。
- multi-turn workflow sequence。
- missing-data / wrong-stage request。
- ambiguous user intent。
- invalid parameter。
- recovery after validation failure。
- state update after backend execution。
- Data Interpretation validation：`safe`、`needs_confirmation`、`blocked`、recipe reload 和
  BIDS folder scan。

case 數量目標：

- engineering baseline：至少 `50` 個 tool-call cases。
- thesis candidate：至少 `100` 個 tool-call cases。
- 每個主要 workflow stage 至少 `10` 個 cases。
- negative / blocked / missing-parameter / recovery cases 至少佔 `30%`。
- multi-turn workflow cases 至少 `15` 個。
- local LLM primary / fallback runner 至少重跑 `3` 次；不足時只能標成 exploratory。

目前 Goal 1 已有 engineering runner：primary / fallback 都已用同一份 `54` cases 重跑 `3` 次，
但 pass rate 仍只有 `33.33%` / `37.04%`。這代表 runner 和 failure taxonomy 已建立，
不代表 tool-call 準確率已達 thesis-ready。

這套 scoring system 才是 thesis evidence 的核心之一；dashboard clean 只能證明工程健康，不能替代 tool-call 準確率評估。

## Target control loop

目標 agent 不是一次 prompt 直接打 backend。它應該是一個有狀態、有驗證、有回饋的 control loop：

```mermaid
flowchart LR
    User["User command"] --> Assembler["Context Assembler"]

    System["System prompt<br/>role and rules"] --> Assembler
    Tools["Tool definitions<br/>commands and schemas"] --> Assembler
    Rag["RAG context<br/>few-shot examples"] --> Assembler
    Memory["Memory<br/>conversation history"] --> Assembler
    State["State Manager<br/>workflow truth"] --> Assembler

    Assembler --> Instruction["Complete instruction"]
    Instruction --> LLM["LLM Agent"]
    LLM --> Proposal["Proposed tool call"]
    Proposal --> Verify{"Verification Layer"}

    Verify -->|"valid"| Backend["Backend command<br/>execute and refresh UI"]
    Backend --> Result["Structured result"]
    Result --> State

    Verify -->|"invalid"| Correction["Self-correction<br/>reflect or ask user"]
    Correction -.-> Assembler

    classDef input fill:#f8fafc,stroke:#64748b,color:#111827;
    classDef main fill:#eef2ff,stroke:#4f46e5,color:#111827;
    classDef safety fill:#fff7ed,stroke:#ea580c,color:#111827;
    classDef output fill:#ecfdf5,stroke:#059669,color:#111827;

    class User,System,Tools,Rag,Memory input;
    class Assembler,Instruction,LLM,Proposal,State main;
    class Verify,Correction safety;
    class Backend,Result output;
```

這張圖定義的是目標設計，不代表目前程式碼已完整符合。

## Context Assembler

Context Assembler 的責任是把使用者指令轉成 LLM 可以判斷的完整上下文。

它應組合：

- system prompt：agent 角色、工作流規則、安全邊界。
- tool definitions：目前 backend command、schema、前置條件、輸出格式。
- RAG context：少量可驗證的 few-shot workflow examples。
- memory：conversation history 和使用者當前意圖。
- state snapshot：由 State Manager 提供的 workflow stage、資料狀態、訓練狀態和可用 command。

Context Assembler 不應直接執行 backend 操作。它只負責讓 LLM 在正確上下文中提出候選 tool call。

## State Manager

State Manager 是 assistant 看到的 workflow truth。

它不應只是聊天記憶，而應整理 app 本體狀態：

- workflow stage：empty、data loaded、preprocessed、dataset ready、training、trained 等。
- data state：raw、preprocessed、epoch、dataset 是否存在。
- training state：是否正在訓練、是否已有模型、是否有 evaluation result。
- UI / command availability：目前哪些 command 可以執行，哪些需要先完成前置步驟。
- recent tool result：上一個 command 成功、失敗、錯誤類型和可恢復建議。

State Manager 的輸出會回饋到 system prompt 和 tool definitions。這代表 prompt 不是靜態文字，而是會跟著 app 狀態縮小或調整可用操作範圍。

## Verification Layer

Verification Layer 是 LLM 和 backend command 之間的安全邊界。

它應在執行前檢查：

- intent 和 tool 是否匹配。
- tool 是否允許在目前 workflow stage 執行。
- required inputs 是否完整。
- input schema、型別、範圍是否有效。
- file path、dataset、label、model、training option 是否存在或可解析。
- Data Interpretation validation 是否允許資料解讀套用；`needs_confirmation` 要先問使用者，
  `blocked` 要停止。
- ApplicationService capability policy 是否仍允許此 command。
- destructive / long-running command 是否需要 human confirmation。
- agent confidence 是否足夠；不足時可重送 prompt、self-correct 或 ask user。

驗證失敗時，不應直接吞掉錯誤或硬跑 backend。它應產生可回饋給 LLM 的 structured error，讓 Self-Correction 重新檢查 intent、補參數或向使用者提問。

這裡的 confidence gate 只屬於 agent control loop，用來提升 tool-call 準確率與降低低信心亂呼叫。
它不能覆蓋 backend / Data Interpretation validation。若資料解讀 validation 是 `blocked`，
即使 LLM 對 tool call 很有信心，也不能執行 apply；若 validation 是 `needs_confirmation`，
agent 必須把需要確認的語意交給使用者。

## Autonomy Policy / Decision Boundary

agent 可以協助使用者完成一整段 workflow，但底層執行必須是一個 command 一個 command
地驗證、執行、刷新 state，再決定下一步。

目標不是把 agent 限制成只能做單步，也不是讓它一次吐出多個 tool call 盲跑到底。成熟模式是
verified workflow operator：

```text
user goal
  -> agent proposes a workflow plan
  -> propose one tool call
  -> Verification Layer checks tool call
  -> ApplicationService executes command
  -> backend returns state + capability + autonomy decision
  -> agent continues, asks user, retries, or stops
```

這裡需要在 workflow state 之上再加一層 autonomy policy：

| 層級 | 責任 |
| --- | --- |
| Workflow State | 描述目前有什麼資料、epoch、dataset、training result、active job。 |
| Capability Policy | 描述 backend 目前允不允許某 command 執行，以及 blocked reason。 |
| Autonomy Policy | 描述即使 command 可執行，agent 能不能自動執行；執行後能不能繼續；什麼時候必須停下來問使用者。 |

`can_execute = true` 不等於 `agent_can_auto_execute = true`。例如 `start_training` 在 backend
state 上可能可執行，但它是 long-running / high-impact command，agent 仍必須要求確認。

每個 command 都應有 command-specific autonomy policy：

| 欄位 | 含義 |
| --- | --- |
| `can_auto_execute` | agent 是否可在沒有使用者再次確認時執行。 |
| `requires_confirmation` | 是否必須 human confirmation。 |
| `decision_boundary` | 是否碰到語意、破壞性、長任務或高影響邊界。 |
| `continue_allowed_after_success` | 成功後 agent 是否可以自動進下一步。 |
| `retry_limit` | 此 command 的自動修正 / retry 次數。 |
| `stop_after_success` | 成功後是否必須停下來回報或詢問。 |
| `blocks_downstream_until_confirmed` | 未確認前是否阻擋下游 workflow。 |

建議的基本 policy：

| 類型 | 例子 | policy |
| --- | --- | --- |
| read-only query | get state、list files、preview、explain validation | 可自動執行；成功後可繼續。 |
| scan / candidate construction | scan source、infer metadata、build interpretation candidate | 可自動執行；只能產生 preview / candidate，不可直接套用語意。 |
| semantic confirmation | subject map、session map、class map、event role、label anchor | 只要不明確就停；`needs_confirmation` 不自動 apply。 |
| data apply | apply interpretation、apply label/event mapping、save recipe | `safe` 可執行；若影響 downstream truth 或來自推論，應要求確認。 |
| data transform | preprocess、epoch、generate dataset | 可依明確設定執行；缺參數或策略不明就問使用者。 |
| high-impact strategy | split strategy、training mode、model choice、saliency target | 預設停下來確認，不靠 agent 自己猜。 |
| long-running | start training、large evaluation、model download | 一律確認；執行後顯示進度與可恢復狀態。 |
| destructive / lifecycle | reset、new session、clear dataset、remove files | 一律確認；不可自動 retry。 |
| blocked | capability blocked、Data Interpretation blocked、resource locked | 不 retry，不硬跑，直接回報可理解原因。 |

停止條件不應是「state 一改變就停」，而是碰到 decision boundary 才停。

典型例子：

- scan source 成功：可以繼續 preview。
- preview 發現 subject / session / class map / event role 有歧義：停，請使用者確認。
- apply interpretation 成功：可以建議下一步，但不直接跳到 training。
- preprocess 成功：可建議 epoch；若 epoch window / event id 不明，停。
- dataset 生成前：split strategy、subject-wise / session-wise claim、training mode 不明時停。
- start training 前：一律確認。
- reset / new session / clear 前：一律確認。

建議的 turn-level guard：

```text
max_self_correction_attempts = 2
max_tool_failures_per_turn = 2
max_successful_tools_per_turn = 5
max_repeated_same_call = 1
```

這些數字是目標預設，不是不可調參數。更重要的是每個 command 要有自己的 policy，不應只靠
全域 retry 次數。

## Target contracts

以下 contract 是目標外框，不是最終完整 schema。具體 command 欄位要等 Application Service / Command API 第一版切片出來後再定。

### State Snapshot Contract

State Snapshot 是 State Manager 輸出給 Context Assembler、Verification Layer 和 scorer 的狀態快照。

它至少應包含：

- `workflow_stage`：目前整體 workflow 摘要，例如 `empty`、`data_loaded`、`preprocessed`、`dataset_ready`、`training`、`trained`。這只能作為 summary，不能作為唯一狀態模型。
- `data_state`：目前 active dataset pipeline 的 raw、preprocessed、epoch、dataset 是否存在，以及目前資料的基本 metadata。目標先維持一次只有一個 active dataset pipeline。
- `interpretation_state`：目前是否已有 scan result、interpretation candidate、validation decision、applied interpretation 和 recipe；這是資料入口的主要 truth。
- `label_state`：event / label mapping 是否存在、是否和資料相容。
- `training_state`：是否正在訓練、是否已有 model、是否有 metrics / result。長期應能描述多個 training job / experiment run。
- `visualization_state`：目前是否具備可視化前置條件，例如 trained model、channel info、montage；應能指向特定 trained result，而不是只看全域 `trained` stage。
- `capability_policy`：由 backend / Application Service 產生的 command gate，列出目前允許、阻擋、需要確認的 command。
- `autonomy_policy`：由 backend / Application Service 產生或整理的 agent 自主執行邊界，列出
  command 是否可自動執行、成功後是否可繼續、是否需要確認與停止原因。
- `available_commands`：目前允許執行的 command / tool。這是 backend capability policy 的輸出，不是把所有 tool 丟給 agent 後讓 agent 自己猜。
- `blocked_commands`：目前不能執行的 command，以及 blocked reason。這主要給 Verification Layer、scorer、debug 和 UI 診斷使用，不代表要把完整 blocked list 塞進 LLM prompt。
- `active_jobs`：目前正在跑的長任務，例如 training、資料處理或 evaluation。
- `completed_runs`：已完成的訓練 / evaluation / visualization result，可供比較、重用或後續分析。
- `last_tool_result`：上一個 command 的 success / failure、error category 和可恢復建議。

重要原則：State Snapshot 不能成為第二份 backend truth。它應從 Application Service / Study / managers 讀出，而不是自己維護一套獨立狀態。

另一個重要原則：command gate 應由 backend / Application Service 控制。agent 可以提出意圖和候選 tool call，但不能拿到所有 tool 後自行決定哪些一定可執行。Context Assembler 應只把目前 policy 允許或需要確認的 capability 暴露給 LLM；Verification Layer 仍要在執行前再次檢查。

`blocked_commands` 可以保留在完整 State Snapshot / capability policy 中，但 Context Assembler 應保守使用：只在和當前 user intent 相關時，把 blocked reason 摘要給 LLM。完整 blocked list 應優先給 verifier、scorer、debug report 和 UI diagnostics。

workflow state 不應只用一個 stage 字串描述，但目標也不是同時開多個 active dataset。比較合理的模型是：

- 一次只有一個 active dataset pipeline。
- epoch / dataset 形成後，不應把 `load_data` 或 `generate_new_dataset` 當成一般可用 command，避免覆蓋或污染目前 pipeline。
- 同一個 dataset 可以產生多個 training run / evaluation result。
- 已完成的 run 可以看 evaluation / visualization / saliency。
- 使用者可以比較不同 run。

但這不代表所有 command 都可以並行或任意執行。每個 command 仍有 dependency gate：

- 沒有 applied data interpretation，不能 preprocess。
- 沒有 label / event 對齊，不能產生可信 dataset。
- 沒有 dataset，不能 start training。
- 沒有 trained result，不能跑 saliency / model-based visualization。
- 某個 resource 正在被 long-running job 寫入時，不能同時對同一個 resource 做破壞性操作。
- epoch / dataset 形成後，如果要載入新資料或開新 dataset，必須走明確的 reset / new session / fork 類 command，且需要使用者確認。

因此 `workflow_stage` 只是摘要；真正的 State Snapshot 應以 active dataset pipeline、jobs、results 為核心，並由 capability policy 逐一判斷每個 command 對特定 resource 是否可執行。

### Tool Call Contract

Tool Call Contract 是 LLM 提出的候選操作格式。

它至少應包含：

- `intent`：使用者意圖的結構化描述。
- `tool_name`：候選 tool / command 名稱。
- `arguments`：符合 tool input schema 的參數。
- `target_resource`：此 tool call 要操作的資料、dataset、training job、model 或 result。
- `confidence`：LLM 對此 tool call 的信心。
- `assumptions`：LLM 做出的假設，例如預設資料、預設 channel 或預設 training option。
- `requires_confirmation`：是否涉及 destructive / long-running / high-impact 操作。
- `autonomy_request`：agent 希望自動執行、詢問使用者、或只做 preview 的意圖。
- `reason`：簡短說明為什麼選這個 tool。

Tool Call Contract 不應直接等於自然語言回覆。自然語言可以附帶說明，但 scorer 和 verifier 應讀 structured tool call。

`confidence` 不是資料正確性的分數。它只表示 LLM 對自己提出的 tool call 是否有把握，供
Verification Layer 決定是否 retry、reflect、ask user 或繼續檢查 backend policy。資料解讀是否可套用
仍由 Data Interpretation validation 的 `safe`、`needs_confirmation`、`blocked` 決定。

### Verification Result Contract

Verification Result Contract 是 Verification Layer 對候選 tool call 的輸出。

它至少應包含：

- `valid`：是否允許執行。
- `decision`：`allow`、`block`、`repair`、`ask_user`、`confirm`。
- `policy_source`：允許或阻擋此 command 的 backend capability policy 版本 / 來源。
- `blocked_reason`：被擋下的原因，例如 wrong stage、missing data、invalid parameter、unsafe action。
- `missing_inputs`：缺少哪些必要參數。
- `normalized_arguments`：驗證後可交給 backend command 的參數。
- `required_confirmation`：需要使用者確認的原因與確認訊息。
- `autonomy_decision`：`allow_auto`、`confirm`、`ask_user`、`stop`、`repair`、`block`。
- `decision_boundary`：若需要停下，說明是 semantic、high-impact、long-running、destructive、
  blocked、missing-input 還是 resource-lock。
- `continue_allowed_after_success`：若執行成功，agent 是否可自動提出下一個 command。
- `suggested_repair`：給 Self-Correction 的修正建議。
- `verifier_notes`：可寫入 report 的診斷資訊。

這個 contract 是防止 agent 直接亂跑 backend 的主要邊界。

### Scoring Contract

Scoring Contract 是 thesis evaluation 工具用來評分的資料格式。

每個 benchmark case 至少應包含：

- `case_id`。
- `user_command`。
- `initial_state`。
- `target_resource`。
- `expected_intent`。
- `expected_tool_name`。
- `expected_arguments`。
- `expected_verification_decision`。
- `expected_state_delta`。
- `expected_error_category`，若此 case 是錯誤或 recovery case。

每次 run 至少應產生：

- `actual_tool_call`。
- `verification_result`。
- `backend_result`，若有執行 backend command。
- `state_before` / `state_after`。
- `capability_policy`。
- `score_breakdown`：intent、tool、parameters、verification、state transition、error recovery。
- `failure_category`。
- `notes`。

scorer 的目標不是只給一個總分，而是能指出 agent 是錯在意圖理解、工具選擇、參數、狀態判斷、執行結果，還是錯誤恢復。

## Tool Taxonomy

tool surface 不應被舊工具 taxonomy 綁住。成熟 tool taxonomy 應以 workflow intent、
side effect、decision boundary 和 result contract 來設計，而不是以目前檔案所在模組或舊
controller method 命名。

目標 tool 類型：

| 類型 | 代表 tools | 用途 |
| --- | --- | --- |
| Discovery / Query | `get_state`、`list_sources`、`explain_validation_state` | 讀狀態、查詢資料、向使用者解釋目前為什麼可做或不能做。 |
| Data Interpretation | `scan_source`、`preview_interpretation`、`validate_interpretation`、`apply_interpretation`、`save_recipe`、`reload_recipe` | 資料匯入、label / event、BIDS、metadata、recipe 的共同入口。 |
| Metadata Resolution | `infer_metadata`、`preview_subject_map`、`confirm_subject_map`、`confirm_class_map`、`confirm_event_roles` | subject/session/task/run、class map、event role、label anchor 的語意確認。 |
| Data Transform | `apply_preprocess`、`create_epoch`、`generate_dataset` | 對資料做受控轉換，必須綁定 AppliedInterpretation 與 capability policy。 |
| Experiment Setup | `configure_model`、`configure_training`、`select_split_strategy`、`configure_saliency` | 設定高影響策略，通常需要使用者確認。 |
| Execution | `start_training`、`run_evaluation`、`run_saliency`、`stop_job` | 長任務與 job lifecycle。 |
| Lifecycle / Destructive | `reset_session`、`new_session`、`clear_dataset`、`remove_files` | 破壞性或改變 active pipeline 的操作，一律 confirmation。 |
| UI Routing | `switch_panel`、`open_result_view`、`show_import_preview` | 純 UI 導航，不應承載 backend workflow logic。 |

tool 的輸出應該是 structured result，而不是只靠自然語言。

每個 tool 應明確標示：

- input schema。
- required state。
- side effect。
- result schema。
- error category。
- 是否需要 confirmation。
- autonomy policy：是否可自動執行、成功後是否可繼續、retry limit、decision boundary。

tool 重構的完成條件：

- mutating agent tools 不再直接呼叫 controller。
- UI 和 agent 對同一 workflow 使用同一套 `ApplicationService` command / capability policy。
- 資料入口工具以 Data Interpretation command 為核心，不再把舊 `load_data` / `attach_labels`
  當成新 UI / agent 的主要心智模型。
- tool 類型改成上面的成熟 taxonomy；舊 `dataset / preprocess / training` 粗分類只能作為內部模組，
  不能作為 agent 對使用者與 scorer 的主要 tool contract。
- 每個 tool call 都能產生 Verification Result、CommandResult、visible response 和 scoring
  artifact 所需欄位。
- Verification Layer 是執行前必要邊界，不是 prompt 裡的建議文字。
- scorer 可以讀到 state snapshot、proposed tool call、verification result、backend result 和
  visible response。
- raw backend exception / schema 不直接顯示給使用者。

## 和 backend 重構的關係

agent redesign 不應早於 backend command surface。

合理順序是：

1. 先完成全盤架構複盤。
2. 盤點 backend controller workflow logic。
3. 建立 Application Service / Command API 的第一個可用切片。
4. 讓 agent tools 包 command，而不是直接包 controller。
5. 建立 State Manager 和 Verification Layer 的第一版 contract。
6. 建立 State Snapshot、Tool Call、Verification Result、Scoring 的第一版 schema。
7. 建立 agent tool-call scoring system。
8. 再做 tool-call validation 和 thesis evidence collection。

## 目前不能宣稱

- 不能宣稱真 local LLM 長時間 ChatPanel walkthrough 已完成。
- 不能宣稱 tool-call workflow 已完整驗證。
- 不能宣稱 State Manager / Verification Layer 已完成。
- 不能宣稱 tool-call 準確率已被 thesis-grade 評估。
- 不能把 mock tool tests 當成 real workflow evidence。
- 不能把 dashboard PASS 當成 agent thesis claim 已成立。
