# Agent 目前架構

最後更新：`2026-09-28`

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
  +--> LLMController (via queued command dispatcher)
           |
           +--> AssistantTurnOrchestrator
           +--> AssistantToolAttemptSession
           +--> ProcessRAGRetrieverLifecycle
           +--> AgentWorker / LocalRuntimeProcessOwner --> LLMEngine (child process)
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

以下描述目前 source 的責任邊界，不表示整合中的模型契約已完成可用性或交付驗收。

## 主要位置

| 區域 | 目前責任 |
| --- | --- |
| `XBrainLab/ui/chat/` | chat panel、使用者輸入與 local runtime setup／model UI。 |
| `XBrainLab/ui/components/agent_manager.py` | UI 和 assistant 的 composition/presentation adapter；組合窄 lifecycle、dispatcher、publication 與既有 UI handoff owners。 |
| `XBrainLab/ui/components/assistant_command_dispatcher.py` | assistant controller thread ownership、queued shutdown、timeout retry 與 lifecycle cleanup。 |
| `XBrainLab/ui/components/assistant_runtime_lifecycle.py` | local runtime activation、terminal close、recoverable error 與 immutable runtime state。 |
| `XBrainLab/ui/components/assistant_application_publication_coordinator.py` | 將 revisioned application publication 與 training terminal notice 投影到 Assistant。 |
| `XBrainLab/llm/agent/controller.py` | 組合 agent turn：context、parser、verification、confirmation 與 bounded tool execution；不再保存 writable lifecycle aliases。 |
| `XBrainLab/llm/agent/pending_interaction.py` | 管理 blocking confirmation／GUI handoff 的 correlation 與解決結果；不保存對話操作草稿。 |
| `XBrainLab/llm/agent/turn.py` | generation request、turn correlation／delivery 等 immutable DTO；不擁有草稿或執行 policy。 |
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

`ChatController` 擁有唯一 typed conversation history；`ChatPanel` 負責 runtime／turn／composer
與 confirmation 呈現。`ChatTranscriptView` 是完整的 Qt viewport owner，擁有訊息 widgets、
layout、分批 replacement、六個 timers、reader anchor 與 follow-tail；不保存另一份可變 history
或 runtime policy。四個既有 transient surfaces 共用 viewport，內容仍由 Panel 負責；三個窄
signals 協調 surface fitting、content presence 與先捕捉 anchor 再清卡的 replacement 順序。
Capture scripts 讀取同一 viewport 的可見訊息，不經舊 Panel append／layout 相容入口。

### 2. AgentManager

`AgentManager` 是 UI 和 agent runtime 的 composition/presentation adapter。

它負責：

- 透過 runtime lifecycle 與 command dispatcher 建立、啟動及關閉 `LLMController`，而不是直接擁有 worker process 細節。
- 將 chat panel 的 typed turn 交給 dispatcher，並將 assistant presentation、activity 與錯誤狀態送回 UI。
- 透過既有 UI handoff host 處理 switch panel、montage、設定與 confirmation，不在 chat 裡建立第二套 workflow form。
- 由 runtime lifecycle 將選定模型解析為 immutable `AssistantRuntimeLaunchSpec`，不以 UI label 判斷 runtime identity。
- 組合既有 `AssistantApplicationPublicationCoordinator`，由它持有 Assistant 的 rendered
  revision、observer bridge、retry timers 與相關聯的 training terminal notice；Manager
  僅提供 status／terminal rendering 和 turn idle 查詢。Assistant 不替 Desktop acknowledge
  publication delivery；Desktop 的 revision acknowledgement 仍由原 Desktop renderer 擁有。

使用者與 diagnostic turn 都先預約 generation，再取得 runtime 的 exact correlation，最後才
改 transcript。正式 transport 的 accepted 回覆透過 Qt queue，在提交返回後才由 GUI 接收；
UI 不另建 synchronous event FIFO。generation／lease／stale／Stop fences 仍由同一 turn-state
owner 管理。保留兩個 presentation 入口是因為 composer 與 debug rejection／copy 不同，
不是兩套 admission 或 application policy。

UI side effect 仍由 structured tool result 的 UI request 交給 `AgentManager`，但會沿用既有 dialog；
request 打開後 workflow 會停止並顯示 waiting state，不會繼續猜測使用者選擇。

### 3. LLMController

`LLMController` 是 agent turn 的組合層；mutable lifecycle 已有明確 owner。

Desktop dispatcher 將 controller 搬至 `AssistantCommandThread`；在 construction 時連接的
RAG／worker 回呼必須宣告為 Qt slots，讓 chunk、terminal、runtime 與 stop acknowledgement
跟隨 controller affinity。模型完成後的同步工具計算留在該 command thread，不占用 GUI；
GUI 透過既有 typed activity／result signals 顯示狀態，並在真正結果返回後完成 turn。
產品與 capture 的 QObject controller 都走同一 queued transport；dispatcher 不要求
controller 另有 generation worker，也不提供給非 QObject 假物件的同步執行分支。

工具 handoff 的名稱／command／decision fields 驗證與 request 建構由既有 `ui_handoff` 模組
依 canonical registry 完成；controller 只發送有效的 typed request。`ToolAttemptCoordinator`
由自己的 decision/context 建立 confirmation risk、參數與 publication generation；
`ConversationHistory` 選出排除 host feedback 的最近 human request。RAG result 的
cancelled／turn-id／waiting 接受條件由 `AssistantTurnOrchestrator` 決定，controller 仍保留
Qt processing／closing admission。這些內部責任移交不新增工具或改變 confirmation policy。

它負責：

- 建立 `ToolRegistry` 並註冊 real tools。
- 組prompt：strict policy、stage-published action schemas、必要 application state／
  最新 user 原文，另附放得下的 RAG；不投影先前 user／Assistant 對話。
- 讓 `AgentWorker` 在 background thread 生成回覆。
- 用`CommandParser`接受 exact 兩欄 JSON response（`tool_name`、`parameters`），可有整份回答單一 `json`／無語言 code fence；
  只解除外框，原始輸出照存，不做散文抽取、寬鬆 schema 或 legacy fallback。
- 初次生成最多加一次既有格式修復；同一修復仍失敗即停止，不重送第二次相同策略。
  多個完整物件維持 choose-one terminal，已交付操作、確認取消與執行失敗不由格式重試重送。
- `respond_to_user`只呈現回答；其他工具由`ToolAttemptCoordinator`核對publication、
  適用的方法來源與`VerificationLayer`的完整required/type/enum/range，再進執行admission。
- 套用 ApplicationService capability gate，避免 assistant 在錯誤 backend state 呼叫不該開放的工具。
- 將已驗證的單一 tool 交給 `ToolExecutionCoordinator`；mapped workflow tool 透過
  `execute_application_tool_command(...)` 執行 ApplicationService command，直接取得
  `CommandResult` payload。
- tool command lifecycle signal 只更新 Assistant 的 working / terminal presentation。Product
  workflow panels 由 revisioned `ApplicationViewPublication` 更新，不以 serialized
  `changed_state` 另做一次 repaint；command 完成後 agent 會重讀同一份 ApplicationService
  state / capability publication。
- 處理 destructive / long-running tool 的 human confirmation。
- 每個 user turn 最多一個工具操作；`respond_to_user` 只呈現訊息，terminal 後不自動接續。

Controller 不再透過 `_active_generation_id`、`_retry_count` 等 writable compatibility alias 保存
第二份狀態。Host/RAG/generation/cancellation correlation 只在 `AssistantTurnOrchestrator`；format
retry、tool execution count 與 visible response 只在
`AssistantToolAttemptSession`。Architecture gate 會以 AST 同時掃 production controller 與測試
fixture，避免測試寫入無效 instance attribute 後產生假通過。

`ToolExecutionCoordinator` 只接收 study、registry、metrics 與三個 lifecycle/status callbacks，
不持有整個 Controller；它在既有 execution module 綁定 reviewed publication generation。
Controller 保留 missing-generation 拒絕與 Qt delivery。有效 proposal 只執行一次、等待互動或
結束回合；format retry 發生在有效 proposal 之前，因此舊 repeated-proposal history／loop-break
分支已移除，不影響 strict-envelope retry 或 one-action admission。

「重試」有三個不同邊界，不能統稱 Agent 自動修復：

- 模型輸出格式錯誤：預設最多額外生成一次（加上首次共兩次），只修正 strict JSON envelope；
  多個 action 直接要求使用者選一個，不執行或重試其中任何一個。
- 工具／backend 執行失敗：回報結果並結束 turn，不把錯誤再交模型重新規劃或自動執行。
  既有確認／GUI handoff 是等待使用者的相關聯回覆；確認後仍重查 publication，不是模型重試。
- 停止／關閉失敗：既有 lifecycle 保留 runtime ownership 並重試資源清理，不代表重跑工具。

`AssistantGenerationRequest` 一律使用 structured-decision decoding；普通說明也由 strict
`respond_to_user` response 呈現，沒有 bypass parser 的 natural-language selector。Core 的
`INFORMATIONAL_TEXT` 仍供獨立 runtime inspection 使用，不是 Assistant turn 的第二條路徑。
Parser保留status、error、message與單一command tuple；derived decision僅供語意診斷。
`proposal_dict()`只投影合法兩欄回覆；`NO_TOOL`不帶command。ParameterChange、
RequestUpdate與舊commands／pending_action／missing_inputs介面均已移除。
Recovery artifact 仍使用七個
現行 taxonomy 字串；其中 `first_attempt_plain_text`／`recovered_plain_text` 指合法 structured
回覆，不表示接受任意裸文字。已無 producer 的 blocked／missing-input／answer 六種舊分類已移除。

舊 heuristic confidence 已移除：它不是模型校準機率，而且 strict parser 接受的合法 current
tool proposal 都能通過唯一產品門檻。Schema、value origin、capability、confirmation 與
publication 檢查仍各自保留，沒有用另一個估分層取代它。

Controller shutdown 只使用實際 `AgentWorker`／`QThread` 的 acknowledgement、timeout/retry 與
native-exit probe；不再提供專供非 QObject／QThread 測試替身使用的成功路徑。Worker 已釋放／
刪除、RAG cleanup 未完成與晚到的 Stop acknowledgement 仍由原有 lifecycle fence 處理。
RuntimeLifecycle 只消費 dispatcher 的 cleanup 結果，不再同時旁聽 controller shutdown 重送
close。真 walkthrough controller 允許同步 close、沒有 shutdown signal；正常 Controller 的
非同步 shutdown 仍先釋放 worker、還原 affinity、關閉 command thread 後才完成。

Assistant Settings 的 `Restart Assistant` 是明確確認後的恢復入口，與 Save／Disable 分開。
它清除當前對話、以已保存設定重新載入模型；不自動重送要求，不取消已提交的後端工作，
不改 EEG 或 root settings.json。RuntimeLifecycle 共用既有 unload／dispatcher cleanup，
舊 runtime 完整釋放後才建立新 controller；只有新模型 READY 才顯示成功。清理失敗保留
ownership、拒絕舊 controller 回報並允許安全重試；App close 優先，不再建立替代 runtime。
Manager 的 Qt signal ingress 核對 live controller 身分與 initialized 狀態，拒收已銷毀 sender
或舊 generation 的晚到回報。WorkflowUiHandoffHost 只 detach Assistant consumer，保留
Desktop command completion，避免重啟吞掉既有 GUI 工作結果。Settings 只呈現 owner 進度。

UI 不可直接讀 `AgentWorker.engine` 或 generation thread。worker 發出 model id、backend mode、
initialized 與 cleanup_pending 的 snapshot；後者是已不 ready 但仍持有待清理 runtime 的投影，
不是另一份 process owner。`AgentManager`、VRAM conflict check 和 model deletion preflight
都讀 `LLMController.runtime_snapshot()`。architecture guard 會阻擋 UI 回到 worker internals。

這一層目前同時包含 agent orchestration 和一部分 workflow policy。所有 mapped workflow
command 仍由同一個 Study-scoped ApplicationService lock 序列化，避免 UI 與 assistant 同時 mutation。

### 完整單輪要求與參數來源

模型回覆恰好是`{tool_name, parameters}`。一般工具的parameters是完整實參object，
由既有schema驗證；`respond_to_user`的parameters恰好含非空message，不進工具registry
或executor。Parser不接受舊decision／mode／changes提案，也不從回答文字推導操作。

每次普通要求獨立；缺值只回答並請使用者重新提供完整要求，不保存草稿或合併歷史值。
一般說明、裸值與指涉文字仍交同一模型路徑理解；沒有Host intent router、bandpass排序
或免生成補值捷徑。Bandpass／notch／resample數值由模型解析；Host不再要求原句
含相同阿拉伯數字，也不另做英文數字解析。完整schema／range與後端admission仍必須通過。
Reference／normalization方法來源仍只核對最近user原文；Host不以history、RAG或backend
state補值。來源匹配不證明語意、否定或操作意圖正確；RAG示例來源helper未隨Host放行改動。

`PendingInteractionCoordinator`只保存blocking confirmation／GUI handoff。這些互動仍按
typed request identity消費一次；確認後重讀publication，取消、Stop、New Chat與Close不
復活操作。生成失敗、空回覆、格式修復耗盡或輸入超限結束當輪；沒有可保留或恢復的草稿。
背景training及停止仍沿用原有backend與async lifecycle，不是對話累積能力。

### Prompt state projection

目前prompt不使用Host intent narrowing、recommended-next-step或deterministic continuation。
Assistant 已移除曾經重複保存這些資訊的 `decision_context`／turn-authorization shadow；
`ContextAssembler` 從同一份 immutable `ApplicationViewPublication` 投影 backend-owned stage
與必要 state，再依 `STAGE_CONFIG` 發布該 stage 的 approved action schemas。
模型提出`respond_to_user`回答或一個操作；Host 不替模型選前置步驟或自動接續下一個 mutation。

最後一則必要user-role JSON只含`application_state`與`current_user: {text}`，
保留當輪原文，不含source ID或pending。State card仍是assembler內部投影，
送出時轉為required application_state，不作optional state_card。工具catalog的required
約束完整執行參數；缺值不能從歷史或範例填入。固定policy沒有跨輪靜態示範。

模型不接收先前 user／Assistant 對話，也不產生conversation_history參考。
ConversationHistory仍保存畫面／診斷所需內容；assembler只從有界紀錄選出最新有效user
原文。Host feedback、raw action proposal與diagnostic trace仍由producer標記為`internal`，
不成為當輪要求；來源不由`System:`／`Tool Output:`前綴或JSON形狀推論。
可選參考的untrusted-context隔離與redaction保持；不為模型裁剪而刪除畫面聊天紀錄。

完整輸入有兩層界線：assembler 先檢查必要 messages 的序列化 UTF-8 byte bound，再以完整
RAG 範例優先於 optional runtime notes 打包剩餘空間；local backend 以選定模型的
實際 tokenizer＋chat template 計數，輸入預算為 runtime context 減去預留輸出 tokens。
超 token 預算時先移除 optional notes，再按原檢索順序逐個放入仍容納的完整 RAG
範例，不裁切範例欄位。System 與最後的必要 request 不能截斷；它們本身仍超限便回
recoverable precondition error，不呼叫模型。使用者可縮短完整要求，或用New Chat清除對話後重述；
超限不會靜默裁切必要要求，也不等於模型答錯或成功處理。

啟用 runtime capture 時，在上述 role/template 處理與 token packing 之後保存實際 prompt、原始輸出、
模型 revision、生成設定及內容 hash；超限拒絕不產生一次成功推論。完整 context 清晰度與
小模型理解仍須依 [target 驗收要求](../target/agent.md#agent-m0-contract)及實際輸出分開檢查。

### RAG 施工中的檢索與證據邊界

當前施工與阻擋由[active plan](../planning/now.md)擁有，准入契約由
[Agent target](../target/agent.md)擁有。下列既有接點不代表M3或模型收益已驗收；
對稱IDF覆蓋與最終送例相關性gate沿用；目前單輪准入fixture為v5，不把批准當作通過。

Bundled gold set目前有161個英文單輪示範：前一版157筆再補4筆純否定；7筆缺值／
部分值改用直接操作用語，回答指出精確缺項並要求完整重述，不改有效正例與純說明。
兩筆補值／更正多輪示範已移除；缺值回答要求重新提供完整要求。操作涵蓋18個approved
tools；非操作示範包括概念詢問、明確禁止、外部指涉與混合要求先選一件。
範例使用兩欄tool_name／parameters，`RAGConfig`固定corpus hash與index schema 6，
不能重用舊索引。它們是retrieval corpus，不是驗收題庫，也不證明模型準確率改善。

`example_policy`使用同一strict parser、完整工具schema與本筆input來源驗證；
prior_turn一律拒絕。Indexer與BM25只搜尋本筆input，metadata保留source_text；
retriever與assembler重驗後傳送完整`input / expected_proposal`，不推導或接受serialized pending。
範例內的值仍是untrusted data，不能成為目前使用者的要求。

RAG不以手寫intent grammar決定是否檢索；查詢只取assembler投影的當輪user文字，
不加入先前要求、Assistant問句或schema。Dense與BM25依同一eligible corpus獨立
取最多10筆准入候選；dense維持cosine 0.7，BM25沿用全corpus IDF，不受dense門檻否決。
聯集按stable ID去重、等權RRF（rank constant 60）排序，最多送3個完整範例，也允許零例。
`dense_only=True`不建立或查詢BM25；hybrid缺少BM25不silent fallback。
舊dense候選池內加權重排，以及v1原始分數／v2單側query覆蓋的失敗報告保留歷史身分。
V3要求至少兩個不同詞命中，且max(query-IDF覆蓋, document-IDF覆蓋)>=0.5；兩側各用
不同token的同一corpus IDF總和，query的OOV維持df=0。最終送例相關性與分路候選診斷分開記錄，
不能將未送出的近鄰稱為模型收到的範例，也不能將未過gate的規則稱為完成。

回應示範使用既有strict response parser驗證，不加入action registry或backend capability。
檢索等待期間publication可能改變；最終組prompt時，assembler以當次同一份publication
產生schemas／required application_state，並重新檢查RAG範例資格，排除已不可用的action。範例仍是有來源標籤、
有大小上限的untrusted data，不能授予capability或confirmation權限，
也不能替使用者提供缺少的參數。

`scripts/dev/verify_rag.py` 以固定的 36 正例／12 邊界工程探針驗證真離線檢索，沿用產品
assembler 的七個 stage tool publications，不以預期工具單獨過濾候選。Top-3 門檻為 33/36，
每工具至少一題；另檢查 context bounds、未授權工具、索引身分與重用。原48題的輸入保持不變；
說明性問題的retrieval oracle檢查範例資格與邊界，不再強迫空結果。模型是否正確不操作須另驗。
另有24個獨立成對工程探針，記錄action／response命中與相同安全檢查，不加入原36題的分母。
同一verifier另執行固定v5的10＋10單輪准入案例：所有實際送例須在預定相關集合，無關題不得
送例，指定詞法正例須出現在sparse候選；未指定必回例的題目允許零命中。分路錯候選只作診斷，
dense候選未觀測須明示，不能以最後三例倒推整個候選池。固定fixture／corpus hash與index
schema一併識別目前配置；v5保留v4全部query／原有標註，只補新語料的同主題示範ID。
v4只從v3原24題移除4個跨輪案例；舊fixture不覆寫，主題相關不代表當輪應採同一決策。
v1／v2／v3原fixture及失敗報告不改寫。
`--ranking hybrid|dense`使用同一產品retriever比較排序；`--baseline-report`
可比對同一探針／設定的舊報告，並核對逐題資料與摘要一致。這些探針已用於開發修訂，
不是 holdout／正式 Validation 或 Test；檢索命中也不等於模型判斷或工具執行成功。
Baseline比較逐題拒絕pass→fail，不能用新增命中抵銷退步。結案須追查所有已知失敗的
語料、候選／門檻、排序及下游責任；response類別命中仍須檢查範例是否回答同一種問題。
本節描述source與驗證介面，不宣稱本輪真模型收益、BM25消融、Windows手測或交付gate已通過。
Retriever 擁有 Qdrant client 與 embedding；`RAGIndexer` 只借用這兩個資源建索引，
不自行配置或關閉。索引 manifest、point identity 與 payload digest 仍驗證持久化內容，
不是可省略的記憶體快取標記。

### Data Import boundary

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

`AgentWorker` 透過 `LocalRuntimeProcessOwner` 管理獨立子程序中的 `LLMEngine`。
初始化與模型替換共用既有 `RuntimeLoadThread`，不在 worker 的 Qt event loop 同步等待載入；
失敗不把已關閉的舊模型恢復成 READY。Close／cancel 若未能退出，仍保留原 process handle，
後續可重試清理；cleanup_pending 期間禁止把使用中的模型當成可刪除。
設定保存回傳失敗與 runtime 是否已就緒分開處理，不把儲存失敗冒稱成已保存的模型選擇。

子程序內的 `LLMEngine` 只擁有一個 backend，不再維護單 mode 的字典 cache、原地切換或
舊模型 rollback。載入失敗後若 cleanup 未完成，或 unload 失敗，仍保留該 backend 供再次
清理，但不允許生成；真正釋放後才回報 close 成功。子程序循序處理 generate／close，並行的取消監視器只送取消要求，
不是另開一套可同時 load／generate／close 的 engine API。

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
- Download catalog 另含固定 MiniLM embedding asset，不把它加入 selectable LLM catalog。
  Windows source setup 使用同一 download lifecycle／安全檢查，揭露並確認下載，再做 CPU
  離線 model/index/retrieval readiness smoke；generation 與 RAG 分開的 cache 另作合計容量
  檢查。來源、路徑、重跑／清理與安裝證據界線見[本機環境](../developer/local-setup.md)。
  Runtime 僅讀既有 pinned embedding，不在 Assistant turn 自動下載；missing cache 可使
  產品 RAG 停用，但不能替要求 RAG 的論文條件提供有效證據。
- `AgentManager` 首次啟用 local runtime 時只在 Assistant Dock 顯示 inline setup：exact selected model
  label、estimated VRAM、cached model的`Enable Assistant`，或missing cache的`Set up model`與唯一
  `Assistant Settings`入口；不再建立first-run modal，app startup也不會自動載入大型local model。
- runtime resolver 只啟動設定中明確選定且可用的 exact model；若不可用就回 typed unavailable，
  不靜默改用另一個 catalog model。
- `LocalBackend`只接受product catalog的repo id及固定spec；產品不提供研究模型pin或
  template kwargs注入。研究模型配置隨受測source保存在外部封存，不擴張Settings清單。
- `LocalBackend` 固定 `trust_remote_code=False`；CUDA dtype 與 runtime context budget 來自
  immutable spec，本機 settings不能放寬remote-code trust。現行產品模型皆支援
  system role，不再有 `supports_system_role` 欄位或system→user legacy merge。
  Pinned template接受連續user時保留untrusted context與request分訊息；template不接受時
  由既有backend合併相鄰user內容，保留context delimiters與原文順序，不偽造assistant回覆。
  每次 generation 都使用實際 HuggingFace stopping criterion 連到取消
  event；未結束的 generation lease 不因停止 streamer 或 UI turn 結束就釋放。
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
- local model replacement（整個 process 替換）。
- generation timeout。

`LLMConfig` 和 `AssistantRuntimeSelection` 是 runtime truth。UI 顯示文字不能當成真實 backend 狀態。

Assistant 的已接受 bounded baseline 與 promotion 限制由[目前狀態](../current.md)及
[有效決策](../decisions/README.md)擁有；本頁不複製歷史分數或推論目前 cache 狀態。
Host 來源驗證／format recovery 不等於模型自主正確，也不取代真人 workflow 或 thesis evidence。
歷史兩欄／Host receipt及五欄累積契約成績保留原source與report schema身分，不改標為本輪基線。
4-bit loading 仍是 optional path；`accelerate` / `bitsandbytes` 不是預設產品啟動硬需求。

Gemini/API 不再列為產品驗證目標；default dependencies 不包含 remote SDK。
歷史研究的source與fixture由外部研究封存保存，不在產品新增legacy path。

### Response and presentation boundary

普通回覆、空回覆、worker failure、blocked action 與 successful tool 都必須有 typed visible
terminal；diagnostic detail 不洩漏到 transcript。Confirmation card 保留 exact request identity，
不從顯示文字重建參數；Stop／New Chat／Close 不得沿用過期批准。
卡片只呈現action details與既有確認／取消操作，不再投影training snapshot建立舊式
Current／Proposed比較，也沒有該比較專用的Apply／Keep或未驗證提示。Presentation仍以
可用且可靠的publication generation判斷過期警示；真正執行前的admission與重新驗證不由卡片決定。
Workflow panels 只 render revisioned `ApplicationViewPublication`，command-result signal 只管理
Assistant activity／terminal ownership，不以 `changed_state` 另建 repaint 路徑。
Chat 的 widget、scroll、輸入與 inline setup 契約見[UI 架構](ui.md#chat-product-contract)；
真模型、native capture 與人工驗收要求見[驗證契約](../validation/README.md)。

`ChatController`以typed history作為唯一可變transcript；`messages`只是供evidence讀取的
role/content複本，不能反向修改正式歷史。UI只訂閱typed record／history replacement與
processing signals；prune、restore、clear後的reentrant notifications仍依FIFO發布。
逐筆事件只新增已提交的訊息；還原同 ID 的內容由完整 history replacement 更新既有 widget，
沒有另一條產品不使用的 record-update signal。
每個bubble只建立實際prose與code widgets，不保留隱藏的第二份Markdown renderer；
capture檢查全部prose區塊，而非只檢查第一段。Suggestion外觀與固定prompt不隨此內部清理改變。

### 5. Tools

`XBrainLab/llm/tools/definitions/` 定義工具名稱、參數 schema、描述和是否需要 confirmation。

`llm/tools/__init__.py:get_all_tools()`從現有definitions建立工具並驗證完整membership；
實際command執行由`application_surface.py`接到ApplicationService，UI工具產生typed request。
沒有另一個`tools/real/`實作目錄。

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

`ToolCommandResult` 與純結果遮罩／轉換位於 `llm/tools/result_contract.py`；
`application_surface.py` 保留能力適配、應用層結果正規化、command 對映與執行，結果 DTO 不反向依賴它。
正式 tools 只回傳 `ToolCommandResult` 或 typed `UiRequest`；舊 `ToolResult`、結果別名及 raw
`CommandResult` 正規化 fallback 已移除。Command adapter 必須先完成 typed 轉換，其他回傳型別
在執行邊界 fail closed；public projection／compact feedback 仍負責完整公開欄位的遮罩與界限。
這是目前 agent-facing typed result adapter：

- ApplicationService blocked command 會回傳 structured failed result，包含 `command_name`、
  `blocked_reason`、capability 和 state snapshot。
- 五個direct preprocess與四個lifecycle tool把`CommandResult`直接轉成`ToolCommandResult`；
  adapter不保存第二份workflow state或confirmation policy。
- 七個GUI completion tool共用一個thin handoff adapter；trusted action contract固定route與decision
  fields，模型參數永遠是`{}`。只有dialog的completed/cancelled/blocked/unavailable/failed outcome
  能結束turn。
  舊 interpretation／standalone import／train／evaluate／visualize Agent routes 與其 suggestions、
  interpretation identity 傳遞已刪除；通用 backend／GUI 的同名能力不受影響。Model 與 training
  options 各走其正式 dialog，不再提供沒有工具 producer 的 combined／empty settings 分支。
  Lazy panel materialization 的 `NAVIGATED` 與 command-pending progress 保留，但不作成功 terminal。
- `switch_panel`等待MainWindow/subview materialization callback，不把UiRequest emission當成功。
- `compute_saliency`不讓模型填run/method/settings；它等待相同operation的completed/cancelled/failed
  terminal，不把command schedule receipt當成功。
- Data Interpretation、analysis與query services仍供產品GUI/backend使用，但沒有Assistant wrapper。
- 缺少direct tool必要參數時，模型以`respond_to_user`請使用者重新提供完整要求，不保存值；
  adapter不套default、不走legacy fallback。
- `CommandResult` 轉成 typed result 後，history 的 `Tool Output` 只保留 redacted compact feedback：
  `ok`、`tool_name`、`command_name`、`message`、`error_type`、`recoverable`、`blocked_reason`，
  加上有值時的 capability 白名單、`state_summary` 與 diagnostics 白名單；不保存完整
  `raw_result`／state。這是內部 trace，不是下一輪模型的 tool observation；`ContextAssembler`
  依明確 `internal` role排除host feedback，以新publication建構當輪state，不排除同前綴的真人要求。
- `set_montage`保留既有 public tool identifier，但 handoff 走 Dataset panel 的 `Electrode Layout`
  entry；Cancel不產生 montage mutation。Evaluation與Visualization 由`switch_panel`導向既有panel；
  Compute Saliency只觸發既有panel action，不重建readiness或render owner。

## Workflow State Gate

`XBrainLab/llm/pipeline_state.py` 重用 backend 的 `PipelineStage`，提供 prompt stage-to-tool
mapping；不另推斷 Study 狀態，也沒有 mock／legacy direct Study fallback。Prompt、capability
policy 和 command execution 共用 ApplicationService publication truth；真正可用工具與
blocked reason 仍由 backend capability policy 產生。

`ContextAssembler`以backend `pipeline_stage`選擇`STAGE_CONFIG`中的approved target schemas；這是prompt
publication。ApplicationService capability不是另一個prompt router，而是在proposal後再次做authoritative
admission。若 state publication 不可靠，prompt stage 固定為 `unavailable`，
只發布 `switch_panel` 操作；非執行的`respond_to_user`不屬於工具registry。

模型輸出採前述兩欄response，不回填 `workflow_stage`。Stage 在 required
`application_state`／backend publication 中，system 亦保留同一 publication 的簡短 stage
事實；Host 以保存的 generation 驗證 proposal、confirmation 及 execution，不從模型 JSON
取得 state。停止確認綁定原publication的`TrainingRunIdentity`，同場running進度
更新不失效；既有確認DTO同步投影此身分供失效提示使用。批准後由可信執行adapter寫入
`StopTrainingCommand.expected_run`，manager／Trainer在既有鎖內核對相同run仍為RUNNING
才提交interrupt；換run／terminal／stopping拒絕，等待worker在manager鎖外。
GUI無綁定的即時停止仍沿用既有控制路徑；不新增模型參數、確認重試或全域generation例外。
舊五欄／三欄提案不被產品parser接受，沒有雙格式相容路徑。

RAG操作示範都受同一條18-tool與stage publication邊界約束；非執行回答示範以
`respond_to_user`分類，不能授予執行權限。
`example_policy.py`由實際action schemas、strict parser及來源驗證判斷可索引內容，
排除舊dataset-info、direct load／attach、granular preprocess及malformed例子。
Index payload的`decision_name`由驗證後示範推導，作為搜尋篩選欄位而不是第二權限來源；
manifest與payload完整性要求舊索引重新符合目前schema，retriever及最終assembler仍重新驗證。
索引包含跨stage的合法示範，不在建索引時把某一時刻的callable集合固定成永久權限。
RAG專用的`llm/agent/intent.py`已移除；語句不再由另一層規則分派操作／說明，
模型理解當前要求，後端保留authoritative admission。

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
