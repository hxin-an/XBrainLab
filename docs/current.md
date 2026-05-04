# XBrainLab 目前狀態

最後更新：`2026-05-05`

## 摘要

XBrainLab 的 active repo 已在目前 workspace 專案區。標準 `dev,test,docs` 環境可用，fast quality dashboard 已在新路徑刷新，結果是 clean `PASS`。

目前階段已進入 product-delivery engineering。`2026-05-02` 人工驗收曾修正先前的
產品判斷：AI Assistant 當時仍像 debug dock，且一般輸入 `hello` 後沒有任何 assistant
回覆。這代表先前 automated final gate、local runtime smoke、launcher startup smoke、
deterministic eval 都不能被解讀成「可用桌面產品已完成」。

後端 `ApplicationService / Command API` 第一版已落地，並完成 command contract、
capability policy、reset state invalidation 和 facade compatibility 的驗收補強。UI / Agent
command surface 第一批統一也已完成：UI readiness 和 agent tool availability 都開始讀同一套
ApplicationService capability policy，agent tool result 已收斂成 typed adapter。local LLM
runtime 已完成非中國 primary / fallback 模型選型、cache preflight、下載、GPU prompt smoke
和 structured-output smoke；desktop launcher 已產出並完成 startup smoke。

目前 chat release blocker 已完成產品級修復：normal text input 有可見 assistant 回覆，
空回覆 / worker error / local unavailable 都有可見狀態，ChatPanel 已改成使用者導向
產品面板，第一層 UI 不再顯示 raw command names。local assistant runtime 現在有 first-run
consent，使用者明確選擇 Enable / Download / Use existing cache / Later / Disable 前不會
偷偷載入大型模型。

2026-05-03 人工產品審核 follow-up 又補了一輪產品級修正：Assistant dock 頂部不再顯示
chip dump，chat panel 內也不再放 `Conversation` 標題、第二條狀態列或 developer mode
controls。第一層只保留 dock title bar 的單一功能列：`XBrainLab`、retry icon、new
conversation、settings menu、float/dock；`Clear conversation` 收進 settings menu。`Retry`
沒有上一則 request 時預設 disabled，直接呼叫也只顯示 notice/status，不再污染 transcript。
agent visible transcript 不再顯示 `Tool <name> completed (...)`、schema error、empty list 或
snake_case command；raw tool payload 保留在 controller history / diagnostics。Assistant
runtime 已改成 product local-only：API / Gemini backend modules 已從 product package 移除，
settings / worker / engine 不再接受 remote execution mode。

UI action execution 已把 import、preprocess、epoch、split / model / training setting
dialogs、evaluation / visualization / saliency query、training start / stop、reset /
new session、metadata update、smart parse、remove files、label import 和 montage confirmation
這批 path 接到 `ApplicationService.execute()`；agent mapped tools 也可直接取得
`CommandResult` payload。新增 `LabelImportPlan`、`apply_montage` 和 `query_state`
讓 UI / agent 不必繞 controller 拿 typed result。本輪新增 split audit / thesis protocol
artifact schema，讓 train/validation/test split 可保存、重跑、審計。2026-05-03
`Backend Workflow Contract v2` 第一個切片新增 reset/cleanup lifecycle commands，
並讓 dataset split apply / audit failure 以 structured `DATA_MISMATCH` failure 回傳且
rollback dataset / generator / trainer state，避免半成功後仍可 train。`evaluate` /
`clear_training_history` capability 也改以 actual training plan history 為準。
2026-05-04 Goal 1 第一個 backend slice 新增 Data Interpretation command baseline：
`scan_source`、`preview_interpretation`、`validate_interpretation`、
`apply_interpretation`、`save_interpretation_recipe`、`reload_interpretation_recipe`
已進入 `ApplicationService / Command API`，並有 `ScanResult`、
`InterpretationCandidate`、`InterpretationPreview`、`ValidationDecision`、
`AppliedInterpretation`、`ImportRecipe` lifecycle object、state snapshot、capability /
autonomy policy 欄位和 recipe reload review flow。這仍只是 backend contract baseline；
2026-05-04 下一個 slice 已把 Data Interpretation command 暴露到 agent tool definitions /
mock / real tools、`application_surface.py` 和 `ContextAssembler` 可見工具集合。agent
controller 現在會讀 backend autonomy policy 的 dynamic confirmation boundary，且
`BackendFacade(study)` 會重用同一個 `ApplicationService`，避免 scan / preview / validate
lifecycle 在連續 tool calls 間遺失。Dataset panel 主要資料入口也已改為
`Interpret Data Source`，會走 scan -> preview dialog -> validate -> confirm/apply。
同日下一個 slice 新增 `backend.application.automation` 和
`scripts/dev/run_application_command.py`，讓 headless / MCP-ready adapter 以 JSON payload
轉 typed command，並回傳 live capability / autonomy / result schema；deterministic
tool-call eval 也已從舊 `21` cases 擴到 `54` cases，包含 Data Interpretation、recipe、
metadata choice、confirmation、blocked、missing-input 和 `15` 個 multi-turn cases。這仍不是
local LLM 真實 tool-call accuracy。下一個 product-completion slice 已新增真 stdio MCP
server baseline：`XBrainLab.mcp.server` 支援 MCP `initialize`、`tools/list`、`tools/call`，
並由 `scripts/dev/run_mcp_server.py` 啟動；tool schema 仍來自
`backend.application.automation.mcp_tool_specs()`，tool call 仍轉成
`execute_automation_payload()` 並只透過 `ApplicationService.execute()` 執行。這代表不再只是
MCP-shaped schema；後續又新增 stdlib-only MCP stdio client walkthrough artifact：
`scripts/dev/capture_mcp_stdio_walkthrough.py` 會從 client process 啟動 prepared XBrainLab
MCP server，完成 `initialize`、`tools/list`、`scan_source`、`preview_interpretation`、
`validate_interpretation`，並保存 `artifacts/mcp/stdio-walkthrough.json` /
`stdio-walkthrough.md`。後續 release config slice 又新增
`scripts/dev/run_mcp_server_for_client.sh`、`scripts/dev/write_mcp_client_config.py` 和
`artifacts/mcp/xbrainlab-mcp.json` / `.md`；committed config 以 Inspector `mcpServers`
stdio 格式啟動 prepared XBrainLab runtime，並有 integration test 透過該 config command
重跑 `initialize` / `tools/list` / `tools/call` walkthrough。Windows-side official Inspector CLI
也已透過 `xbrainlab-windows-wsl` config 跑過 `tools/list`，保存
`artifacts/mcp/inspector-cli-tools-list.json` / `.md`。後續 MCP Inspector GUI click-through
artifact 也已新增：`scripts/dev/capture_mcp_inspector_gui_walkthrough.py` 會啟動 Windows
Inspector + headless Chrome，點擊 `Connect` / `List Tools`，並保存
`artifacts/mcp/inspector-gui-walkthrough.json` / `.md` 和
`artifacts/mcp/inspector-gui-connected.png`；artifact 顯示 `xbrainlab` connected、`wsl.exe`
wrapper、prepared runtime args、Tools panel 和 Data Interpretation tools 可見。這支撐外部
stdio client path、Inspector CLI / release config baseline 和 Inspector GUI click-through
baseline；仍不是 HTTP transport、long-running training through MCP、Windows launcher 真人驗收
或 full MCP client certification。另已新增 non-mocked backend
workflow evidence：synthetic FIF source 會走 scan -> preview -> validate ->
confirmation-blocked apply -> confirmed apply -> save recipe -> reload recipe review ->
preprocess -> epoch -> dataset，並檢查 split audit / train-val-test counts。UI-observable
replay 也有第一份 artifact：`scripts/dev/capture_data_interpretation_replay.py` 會保存
`artifacts/ui/data-interpretation-preview.png`、`data-interpretation-applied.png` 和
`data-interpretation-replay.json`，對照 visible dialog state、dataset panel state 和 command
result。Data Interpretation preview dialog 已硬化成第一版 import wizard review surface：
可見 `Scan -> Preview -> Validate -> Confirm -> Apply -> Save recipe` 流程、source/readiness、
BIDS status、metadata preview、label/event/recipe trace、confirmation 和 recipe save 選項；
apply 後保存 recipe 仍透過 `SaveInterpretationRecipeCommand`。後續 slice 已把 metadata /
class-map review edit 接進同一流程：dialog 的 subject / session / task / run 與 class map
review cells 可產生 `choices`，Dataset action 會在 apply 前 re-preview / re-validate 新
candidate，backend 會把 user override、class map、event roles 寫入 applied interpretation /
recipe trace；UI replay artifact 也已顯示 `S01`、`session-01`、`motor-imagery` 這組
metadata override。最新 backend/UI polish 已把 reviewed subject/session 同步寫回 loaded Raw
wrapper，task/run 保存到 `data_interpretation_metadata` runtime detail，Dataset table 和 downstream
dataset generation 會看到使用者確認過的 metadata，而不是回到 `0 / 0`。human-like walkthrough
artifact 也已刷新，applied state 顯示 `S01` / `session-01`，training readiness 使用 group split
維持 resource-safe dataset readiness。後續 slice 已新增 label carrier review plan：backend preview 會為
MAT、CSV / TSV、BIDS `events.tsv` 和 TXT carrier 建立 label field / MAT variable、anchor、
time model、granularity 候選；wizard 會顯示可編輯的 label carrier review rows，Dataset action
會把使用者選擇 re-preview / re-validate 後保存到 `AppliedInterpretation` /
`ImportRecipe.label_carrier_plan`。UI replay artifact 現在顯示 `trial_type`、`onset`、
`seconds`、`trial` 這組 label carrier choices；後續 slice 又補上可編輯 role：wizard
會把 event role edit 寫成 `choices.event_roles`，也會把 label carrier role 寫進
`label_carrier_choices`。UI replay artifact 現在可見 `class cue labels` 和
`trial_type -> class cue`，backend unit test 也覆蓋 MAT `classlabel` / `cue_onset` / role /
event role 寫入 recipe trace。再下一個 UI polish slice 已把 label carrier review cells 升級成
selector controls：label field、anchor、time model、granularity 和 role 都可用 combo 選擇；
UI replay 顯示人話 `Seconds`、`Trial`、`Class cue labels`，但 recipe choices 仍保存 backend
需要的 `seconds`、`trial`、`class cue labels`。後續 slice 又新增 format capability
boundaries：scan / preview 會列出 GDF、EDF / BDF、EEGLAB、BrainVision、MNE FIF、MAT labels、
CSV / TSV / BIDS events、TXT labels 和 XDF / LSL 的 supported / needs-review / blocked 邊界；
dialog review notes 會用人話顯示這些邊界，XDF / LSL 目前會明確提示 stream selection 尚未在
wizard 內可用。後續 slice 已新增 generated format capability matrix artifact：
`scripts/dev/report_data_interpretation_format_matrix.py` 透過 live `ApplicationService`
`ScanSourceCommand -> PreviewInterpretationCommand -> ValidateInterpretationCommand` 產生
`artifacts/data_interpretation/format-capability-matrix.json` / `.md`，覆蓋 GDF、EDF、BDF、
EEGLAB、BrainVision VHDR / VMRK、MNE FIF、MAT、CSV、TSV、BIDS events、TXT 和 XDF / LSL
stream export 的 capability / validation boundary。這是可重跑的 capability evidence；仍不是
XDF / LSL stream parser 或全格式 real-data manual certification。最新 slice 已把 reviewed
timestamp label carrier apply 接進 Data Interpretation
主線：`load_label_file()` 可使用 wizard 選定的 MAT variable / CSV-TSV-BIDS label column 和
anchor；`apply_interpretation` 會在單一 EEG + 單一 reviewed timestamp CSV / TSV / BIDS events
carrier、已確認且 time model 為 seconds / relative time 時，自動透過既有
`apply_labels_batch` 套用 labels，並寫入 `label_apply` diagnostics、`label_imports` 和
`label_import:timestamp:<n>` recipe trace。UI replay artifact 現在顯示
`label_apply.status=applied`。舊 label import 已降成「Add Labels to Loaded Data」的
service-backed compatibility path；label import 成功後會更新 applied interpretation 的
`label_imports` / `label_carriers` / recipe trace，UI 也會提示使用者可保存更新後
recipe。它仍是「對已載入資料加 label」的 compatibility UI，不是完整 import wizard 內嵌 label
import editor；同日後續 slice 已把單一 EEG + 單一 reviewed MAT / TXT trial-order sequence
carrier + confirmed class map 接到 legacy label import，recipe trace 會寫
`label_import:legacy:<n>`。最新 backend slice 又把 reviewed MAT label + sample-index anchor
接進窄版 anchored apply path：當 wizard 明確選定 MAT `label_field`、MAT `anchor`、
`time_model=sample_index`、`granularity=trial` 和 confirmed class map 時，`load_label_file()`
會把 label / anchor 變成 MNE-style event array，`apply_interpretation` 透過
`apply_labels_batch` 套用到已對應 EEG，並寫入 `label_import:anchored:<n>` recipe trace。這支撐
GDF + external MAT sample-anchor 的窄路徑；仍不是任意 raw trigger selection、非 sample-index
timestamp model 或複雜 anchor reconciliation。最新 slice 已把 Data Interpretation import truth 補進 shared
state snapshot：`ApplicationStateSnapshot.interpretation`、`query_state`、automation / MCP
envelope 和 agent `query_state` tool surface 都會暴露 reviewed `label_carrier_plan`、
`format_capabilities`、`event_roles` 和 `class_map`，避免 UI / recipe 和 agent / headless
看到不同資料入口真相。最新 backend architecture cleanup 又把 Data Interpretation lifecycle
state 和 scan / preview / validate / apply / recipe command handling 從
`ApplicationService` 拆到 `DataInterpretationCommandService`，reviewed metadata / label
carrier side effects 再拆到 `DataInterpretationApplyService`；UI、agent、headless 和 MCP 仍
只透過 `ApplicationService.execute()` 進入，`ApplicationService` 則回到 dispatch /
capability-confirmation gate / state-result envelope 的角色。這降低了 god-object 壓力，但不能
宣稱 backend architecture 已全面乾淨；legacy data / label compatibility path 仍存在，但已
隔離成 focused compatibility service。後續 cleanup slice
已把 `evaluate`、`visualize`、`saliency` 和 confirmed `apply_montage` 拆到
`AnalysisCommandService`；analysis / visualization readiness 不再直接由 `ApplicationService`
承接。另一個 cleanup slice 已把 `configure_training`、`train`、`stop_training`、
`clear_training_history` 和 reset-time training config clear 拆到 `TrainingCommandService`；
model / optimizer / device / training-option snapshot 也不再由 `ApplicationService` 直接承接。
最新 cleanup slice 已把 `generate_dataset`、`clear_datasets`、split config、split audit、
rollback 和 dataset split summary 拆到 `DatasetGenerationCommandService`。最新 reset lifecycle
slice 已把 `reset_preprocess`、`reset_session`、`new_session`、downstream rollback 和
reset-time dependent-state clear 拆到 `LifecycleCommandService`。最新 compatibility slice 已把
舊 `load_data`、`attach_labels`、`import_labels` 和 label helper 拆到
`DataCompatibilityCommandService`，並保留 Data Interpretation recipe trace 更新。最新 data-table
cleanup slice 已把 `update_metadata`、`apply_smart_parse` 和 `remove_files` 拆到
`DataTableCommandService`。最新 preprocess cleanup slice 已把 preprocessing operations 和
`create_epoch` 拆到 `PreprocessCommandService`。最新 state/query cleanup slice 已把
state snapshot assembly 和 `query_state` diagnostics 拆到 `StateSnapshotService` /
`QueryStateCommandService`。`ApplicationService` 現在主要保留 command dispatch、
capability-confirmation gate、result envelope 和 compatibility wrapper methods。最新 UI
runtime bypass cleanup 又修掉兩個 service-success fallback 風險：Dataset panel direct
file import 在 `LoadDataCommand` 成功後不再再呼叫 controller import；Preprocess reset 也改走
`ResetPreprocessCommand`，controller reset 只保留給 mock / legacy `None` adapter fallback。
下一個 UI cleanup slice 又把 Training sidebar 的 destructive cleanup path 收回 command spine：
重新 split 前清 datasets 走 `ClearDatasetsCommand(confirmed=True)`；Clear History 會先要求
使用者確認，再走 `ClearTrainingHistoryCommand(confirmed=True)`，successful service result 不再
落回 controller mutation。
最新 UI autonomy slice 讓 Training sidebar 的 `Start Training` button 也尊重 backend
`train` long-running boundary：當 capability 顯示需要 confirmation 時，UI 會先用使用者語言詢問
是否開始可能耗時且使用 CPU/GPU 的訓練；拒絕時不會執行 `TrainCommand`，service 成功時不再
fallback 到 controller。Automated Qt replay artifact 在
`artifacts/ui/training-start-confirmation/`，它不是 human desktop acceptance。
最新 Data Interpretation boundary cleanup 把 GDF / EDF-BDF / EEGLAB / BrainVision / FIF /
MAT / CSV-TSV / TXT / BIDS events / XDF-LSL format capability matrix 從大型
`data_interpretation.py` 抽到 `DataInterpretationFormats` focused module，scanner /
candidate lifecycle 不再直接承接 format taxonomy 細節。
下一個 Data Interpretation boundary cleanup 又把 subject / session / task / run metadata
resolution、BIDS entity summary 和 recipe metadata rehydration 抽到
`data_interpretation_metadata.py`；大型 lifecycle module 降到約 `928` 行，但 scanner /
candidate / preview / validation / recipe flow 仍在同一 domain module，後續還可繼續拆。
後續 recipe boundary cleanup 又把 `ImportRecipe` serialization、JSON load/write、recipe
rehydration 和 applied interpretation -> recipe builder 抽到 `data_interpretation_recipe.py`；
`data_interpretation.py` 目前降到約 `822` 行，仍保留 scanner、candidate / preview builder、
validator 和 label carrier planner。
最新 label carrier boundary cleanup 把 MAT / CSV / TSV / BIDS events / TXT carrier candidate
planning、user choice normalization、anchor/time/granularity defaults 和 MAT / tabular column
inspection 抽到 `data_interpretation_label_carriers.py`；`data_interpretation.py` 目前約 `581`
行，主要保留 lifecycle dataclasses、scan / candidate / preview / validate 和 metadata override。
最新 review boundary cleanup 又把 `InterpretationPreview` / `ValidationDecision`、preview
payload builder 和 safe / needs-confirmation / blocked validator 抽到
`data_interpretation_review.py`；`data_interpretation.py` 目前約 `463` 行，主要保留 scanner、
candidate builder、metadata override 和 lifecycle dataclasses。這是 backend internal boundary
cleanup，不是 mature import wizard completion。
最新 scanner boundary cleanup 又把 `ScanResult`、`scan_source_path()`、source kind
classification、BIDS source detection、candidate-file traversal 和 scan warning / blocked reason
assembly 抽到 `data_interpretation_scan.py`；`data_interpretation.py` 目前約 `286` 行，主要保留
candidate builder、metadata override 和 applied interpretation lifecycle dataclass。
最新 candidate boundary cleanup 又把 `InterpretationCandidate`、scan + user choices -> candidate
builder、metadata override、event/class mapping 和 candidate recipe trace 抽到
`data_interpretation_candidate.py`；`data_interpretation.py` 目前約 `75` 行，保留 shared
decision enum、`AppliedInterpretation` 和 public compatibility re-exports。
最新 Data Interpretation session-state cleanup 又把 lifecycle object stores、latest-id resolver、
snapshot assembly、clear 和 post-load label import recipe recording 抽到
`data_interpretation_state.py`；`DataInterpretationCommandService` 目前約 `297` 行，主要保留 command
handler orchestration，不再同時承接 state truth。
最新 Data Interpretation UI source-entry slice 讓 Dataset sidebar 明確提供三個資料入口：
`Interpret Data Source`（EEG file(s)）、`Interpret Folder / BIDS` 和 `Reload Import Recipe`。
folder/BIDS root 與 recipe reload 都走 Data Interpretation command path；UI-observable artifact 在
`artifacts/ui/data-source-entry-options/`。這補上 source type entry visibility，但不是 mature
embedded label editor completion。
最新 agent tool-surface cleanup 把舊 `load_data` / `attach_labels` 從 Empty / Data Loaded /
Preprocessed stage prompt 和 primary tool exposure 移除；Context Assembler 會把 backend
capability policy 與 stage allowlist 取交集，避免 backend compatibility policy 把已降權的
legacy tool 重新塞回主 prompt。`load_data` / `attach_labels` 仍在 schema taxonomy、parser /
verification 和 `DataCompatibilityCommandService` 作為 legacy compatibility surface，但新
agent 心智模型已改以 Data Interpretation scan / preview / validate / apply / recipe 為資料入口。
最新 automation / MCP schema cleanup 也把 legacy data-entry boundary 寫進
`AutomationCommandSpec` 和 MCP `tools/list` metadata：`load_data`、`attach_labels`、
`import_labels` 會標成 `legacy_compatibility=True`、`primary_workflow=False`，並列出 Data
Interpretation scan / preview / validate / apply / recipe preferred commands。MCP/headless client
仍可呼叫相容工具，但 schema 不再把它們包成新資料入口主線。
最新 backend slices 又補了 reviewed label carriers
的多檔安全
mapping：當多個 loaded EEG file 能以唯一 normalized stem 對應各自的 reviewed
CSV / TSV / BIDS events carrier 時，`apply_interpretation` 會一次呼叫 `apply_labels_batch`
套用；MAT / TXT trial-order sequence carriers 也會逐檔呼叫既有 `apply_labels_legacy`。如果無法
唯一對應，會保持 skipped 並回傳人可讀 reason，不會把同一 labels 亂套到多個檔案。最新 slice
讓 wizard 的 `Matched EEG` 欄位能保存人工 target mapping；generic `events.tsv` 或
`labels.mat` 在使用者明確指定目標 EEG 後，可只套用到被指定的 loaded file，recipe trace 也會記錄
target / file mapping。下一個 UX slice 已把 ambiguous `Matched EEG` cell 改成 target selector，
讓使用者不必手打 filename。同日後續 UI slice 已讓 Data Interpretation wizard 的 label carrier table 顯示 `Matched EEG`
欄位；單檔 direct match 或多檔唯一 stem match 會顯示對應 EEG 檔名，無法唯一對應則顯示
`Needs review`。UI replay artifact 已刷新，顯示 generic `events.tsv` 對到
`sub-01_task-mi_run-2_raw.fif`。full raw-event-anchor selection / complex MAT/GDF alignment、
full real-data manual compatibility certification、label import 內嵌 wizard 和真人 click-through 仍未完成。
Post-load `Add Labels to Loaded Data` dialog 已補上 target context：dialog 會顯示 labels 將套用到
哪些 loaded EEG files，並提示成功後會更新目前 import recipe trace。這改善 compatibility label
flow 的使用者語意；後續 guard slice 已讓 `Add Labels to Loaded Data` 在沒有 loaded data 時
disabled，tooltip 引導使用者先 interpret data source，且 action 會尊重 backend
`ImportLabelsCommand` capability block。UI replay JSON 也保存 empty-state disabled button 和
applied-state enabled recipe-trace tooltip。它仍不是完整 Data Interpretation 內嵌 label editor。舊
`load_data / attach_labels` 仍不能宣稱已完全退出產品心智模型。
同日後續 slice 新增真 local LLM tool-call runner：
`scripts/agent/evals/run_local_tool_call_eval.py` 會用同一份 `54` cases / scorer 接 primary /
fallback 本地模型 raw output，且每個 case 重跑 `3` 次。當時 artifact 顯示 primary
`microsoft/Phi-4-mini-instruct` 為 `53 / 54` pass、fallback
`microsoft/Phi-3.5-mini-instruct` 為 `53 / 54` pass；這是可重跑的真模型 engineering
evidence，但還不能宣稱 thesis-ready，因為 benchmark 仍只有 `54` cases，不是要求的
`100` thesis candidate cases。`VerificationLayer` 也補上
registered tool schema / required / type / enum 檢查，controller 會在 tool execution 前攔下
可解析但不可執行的 tool JSON。
同日後續 guardrail slice 進一步把 local assistant tool-call failure 轉成產品可用的安全邊界：
`CommandParser` 可解析 top-level tool-call array 和 OpenAI-style function tool call；
`PlaceholderArgumentValidator` 會拒絕模型自造的 placeholder path；`LLMController` 會用最新
使用者意圖和 `ApplicationService` capability policy 擋下「使用者要求的 workflow step 已
blocked，模型卻改叫別的工具硬補」的 substitute tool call。產品 prompt / local eval prompt /
tool schema 也補上 standard preprocess、dataset split、latest-turn/state-authoritative 規則。
探索性 guardrail smoke artifact 顯示 primary `6 / 6`、fallback `6 / 6`。後續 normalizer
slice 把 command-only JSON、bare tool name、舊 `get_dataset_info` state query、latest-turn
substitute、BIDS scan hint、subject override、dataset split defaults、placeholder prose path
和 backend result interpretation 對齊到 verifier / ApplicationService 語意。正式 full local
eval 已重跑 `54` cases x `3`：primary `53 / 54`、fallback `53 / 54`。剩餘 blocker 是
bandpass-vs-standard preprocess 語意，以及 case 數不足 thesis candidate 要求。
最新 product-completion slice 已把同一 scorer 擴到 `100` thesis-candidate cases，覆蓋
Data Interpretation file / folder / BIDS / recipe、metadata choices、relative / missing path、
confirmation、blocked / recovery、多輪 workflow、bandpass-only vs standard preprocess、
dataset split、visualization / saliency readiness 和 query-state cases。正式 local eval 已用
cached non-China local models 各重跑 `3` 次：primary
`microsoft/Phi-4-mini-instruct` `100 / 100` pass，fallback
`microsoft/Phi-3.5-mini-instruct` `100 / 100` pass；runtime classification 皆為 `gpu-ready`，
cache usage `15.34 GB`，no download。這支撐 thesis-candidate tool-call benchmark evidence，
但仍不等於 multi-turn / tool-command ChatPanel workflow、Windows launcher click-through、完整
import wizard 或 MCP HTTP / long-running client workflow 驗收完成。最新 tool-call
best-practices slice 又把 prompt-facing schema、no-call / clarification policy、nested schema
verification、parser / normalizer repair 和 scoring dashboard 對齊 OpenAI Structured Outputs、
BFCL 與 LangSmith trajectory-eval 設計；deterministic baseline、primary local model 和 fallback
local model 都已跑同一份 `117` cases，primary / fallback 各 `3` 次，artifact 顯示
`117 / 117`，`artifacts/agent_evals/dashboard.md` 也列出 model comparison、case family、
metric pass rates、failure taxonomy、worst cases、source path 和 thesis claim boundary。這支撐
目前 benchmark slice 的 thesis-candidate tool-call claim；仍不等於 UI usability、Windows
launcher、雙螢幕 / DPI、長時間桌面 session 或 product completion。後續 ChatPanel local-model UI
walkthrough 已新增一輪真模型可見回覆 evidence：
`scripts/dev/capture_chatpanel_local_walkthrough.py` 會在 `HF_HUB_OFFLINE=1` /
`TRANSFORMERS_OFFLINE=1` 下打開真 MainWindow / ChatPanel，經 UI composer 送出 prompt，走
AgentManager -> LLMController -> AgentWorker -> LLMEngine local backend，並保存
`artifacts/ui/chatpanel-local-ready.png`、`chatpanel-local-response.png`、
`chatpanel-local-walkthrough.json` 和 `.md`。artifact 顯示 primary
`microsoft/Phi-4-mini-instruct` 為 `gpu-ready`、cache `15.34 GB`、visible transcript 無 raw
tool / debug syntax，UI 回到 idle。這證明 true local model 能在 ChatPanel 產生使用者可見回覆；
後續 tool-command walkthrough 又證明同一 UI path 可執行單步 ApplicationService-backed tool：
`artifacts/ui/chatpanel-local-tool/chatpanel-local-walkthrough.json` / `.md` 顯示 local model
執行 `query_state`，executed tool 為 `ok`，visible assistant transcript 是
`Application state snapshot ready.`，沒有 raw `Tool Output`、schema 或 traceback，UI 回到
idle。下一個 multi-turn ChatPanel slice 暴露並修掉一個真多輪 blocker：第一 turn tool output
曾把完整 state JSON 放回 conversation history，導致第二 turn prompt 膨脹到約 `10.7k` input
tokens 並讓 local model timeout。`LLMController._format_tool_output()` 現在只把 compact
tool feedback / `state_summary` / small diagnostics 放回下一輪；新 artifact
`artifacts/ui/chatpanel-local-workflow/chatpanel-local-workflow-walkthrough.json` / `.md` 顯示
兩個 UI turns：第一 turn 執行 `query_state`，第二 turn 在同一 conversation 中正常回覆
preprocessing 說明，input tokens 降到約 `2.46k`，UI 回到 idle。這仍不是完整長時間
tool-command chain 或 Windows launcher 人工 click-through。下一個 tool-chain slice 已新增
真 local ChatPanel Data Interpretation chain artifact：
`scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py` 會建立 synthetic FIF，經可見
ChatPanel composer 要求 local model 依序執行 `scan_source`、`preview_interpretation`、
`validate_interpretation`，並保存
`artifacts/ui/chatpanel-local-tool-chain/chatpanel-local-tool-chain-walkthrough.json` / `.md`
和 ready / turn screenshots。首次真跑暴露模型會把 `latest_scan_id` 這類 schema-derived
placeholder id 傳進工具參數，導致 backend 無法使用 latest state；`tool_call_normalizer`
現在只保留 backend 真生成的 `scan-<n>` / `candidate-<n>` id，其餘 latest/current/id
placeholder 會移除讓 ApplicationService 使用目前 state。修正後 artifact 顯示三個工具依序
`ok`，final interpretation state 有 scan / candidate / preview / validation decision，decision
是 `needs_confirmation`，UI 回到 idle。這支撐短鏈 Data Interpretation tool-command workflow；
後續 pipeline-chain slice 已把同一真 local ChatPanel path 擴到 import-to-dataset：
`scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py` 會自動觀察並核准
`apply_interpretation` confirmation dialog，然後依序執行 `apply_standard_preprocess`、
`epoch_data` 和 `generate_dataset`。首次真跑在 dataset split audit 被擋下，原因是 epoch prompt
只抽到 `left` 單一 event，導致 3 epochs 下 validation split 為空；這個 guardrail 保持不放寬，
改修 `tool_call_normalizer` 讓「events left and right」抽成多個 event ids。修正後
`artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.json` /
`.md` 顯示七個工具全數 `ok`、confirmation dialogs observed `1`、epoch count `6`、dataset
available `True`、dataset count `1`，UI 回到 idle。這支撐真 local ChatPanel 可走
Data Interpretation apply -> preprocess -> epoch -> dataset 的資料管線；仍不支撐 training /
evaluation / saliency 長鏈、自動正式訓練策略或 Windows launcher 人工 click-through。
同日下一個 agent analysis-tool slice 已把 `evaluate`、`visualize`、`saliency` 補成
definitions / mock / real tools，註冊進 ChatPanel controller 的 tool registry，並由
`application_surface.py` 直接轉成 `EvaluateCommand`、`VisualizeCommand`、`SaliencyCommand`。
`CommandParser` 現在接受三個 bare tool names，`infer_user_intent()` 也會把 evaluation request
映射到 `CommandName.EVALUATE`。這解除「backend 有 typed command，但 agent 不能直接使用」的
架構旁路；它仍不等於 ChatPanel 已完成 dataset -> train -> evaluate / saliency 長鏈。
同日 training-readiness walkthrough 又新增一條真 local ChatPanel artifact：
`scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py` 先用 ApplicationService
準備 synthetic dataset-ready state，再透過可見 ChatPanel 依序執行 `set_model`、
`configure_training`、觀察並拒絕 `start_training` confirmation、執行 `visualize` 和
`saliency`，最後對 `evaluate` 顯示「Create a training plan before evaluating results.」blocked
reason。artifact 顯示 UI 回到 idle、training 沒有被啟動、visible assistant text 沒有 raw debug
syntax。這支撐 high-impact training confirmation boundary 和 analysis-readiness tool path；仍不支撐
真 training completion、evaluation metrics 或 saliency view render 完成。
下一個 completion slice 已補上 controlled tiny training artifact：
`scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py` 使用 training-safe
synthetic FIF 和 1.5s epochs，透過真 MainWindow / ChatPanel / local primary model 依序執行
`set_model`、`configure_training`（含 controlled `output_dir`）、觀察並核准 `start_training`
confirmation、等待 1 epoch CPU training 完成，再執行 `evaluate`、`saliency` configure、
`visualize` 和 saliency query。artifact
`artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.json` /
`.md` 顯示 status `passed`、finished runs `1`、evaluation metrics available `True`、saliency
configured / available `True`、UI 回到 idle，visible transcript 沒有 raw tool/debug syntax。這支撐真
local ChatPanel controlled tiny training completion 與 post-training analysis-readiness summary；
仍不等於真人 Windows launcher click-through、完整互動式 saliency/visualization canvas render、
MCP HTTP / long-running client workflow 或成熟 import wizard label editor 完成。同 slice 修正了 saliency `method` /
flat params 到 backend-required `SmoothGrad` / `SmoothGrad_Squared` / `VarGrad` params 的
normalization，`visualization` intent 判斷，saliency readiness query 的 stale params 清理，以及
evaluation panel tiny metrics fallback：chart `tight_layout` failure 只降級為 warning，缺
`torchinfo` 時回傳可理解的 model-summary unavailable message，不再打 traceback。
後續 render slice 已補上真 MainWindow VisualizationPanel 的 Matplotlib canvas evidence：
`scripts/dev/capture_visualization_render_walkthrough.py` 使用 ApplicationService 準備 synthetic
source -> scan -> preview -> validate -> apply -> preprocess -> epoch -> dataset -> configure
EEGNet -> configure saliency -> apply montage -> 1 epoch CPU train，然後打開真 MainWindow 的
VisualizationPanel 並截 `Saliency Map`、`Spectrogram`、`Topographic Map` 三個 tab。
artifact `artifacts/ui/visualization-render/visualization-render-walkthrough.json` / `.md`
顯示 status `passed`、finished runs `1`、metrics available `True`、saliency available `True`，
三個 tab 均有 visible canvas、無 error label，且 figure evidence 皆有 axes / rendered image
artist。3D tab 在 headless/offscreen runtime 現在不再嘗試建立 PyVista `QtInteractor` 而 crash；
同 artifact 會保存 `visualization-render-3d-blocked.png`，可見 blocked reason 是 3D rendering
requires an interactive OpenGL desktop session，且 `plotter_created=False`。這支撐
post-training Matplotlib saliency render UI evidence 和 headless 3D blocked UX；仍不等於
interactive desktop 3D render / PyVista path、ChatPanel 觸發 UI routing render、真人 Windows launcher
click-through、MCP HTTP / long-running client workflow 或成熟 import wizard label editor 完成。後續 runtime probe
`scripts/dev/probe_pyvistaqt_runtime.py` 產生
`artifacts/ui/visualization-render/pyvistaqt-runtime-probe.json` / `.md`；在目前
`DISPLAY=:0` / `WAYLAND_DISPLAY=wayland-0` session 中嘗試建立最小 PyVistaQt plotter，結果為
`blocked`，stderr 是 X `BadWindow`。這支撐「目前 runner session 不能驗證 interactive 3D」；
interactive 3D product render 仍是 blocker。
MainWindow 首次啟動或壞 saved geometry 現在 fallback 到 maximized，不再用過度聰明的
跨螢幕置中當最後保護。Windows launcher 現在有 automated command walkthrough artifact：
`scripts/dev/capture_windows_launcher_walkthrough.py` 會從 Windows `cmd.exe` 執行 Desktop
`XBrainLab.cmd` smoke、從 PowerShell 執行 WSL stdout/stderr smoke，再透過同一 launcher path
跑 bounded `run.py` startup smoke；`artifacts/launcher/windows-launcher-walkthrough.json` /
`.md` 顯示 Desktop command 指向 active repo、PowerShell launcher 可進 WSL、log file 存在、
stdout/stderr 被 mirror、startup 看到 `MainWindow initialized`，且最新 artifact 會強制收集
startup geometry diagnostics，確認 screen count、screen detail、splash geometry 和 main-window
geometry log 都出現。這仍不是真人 Windows
Desktop click-through 或 release packaging approval。真 local model 多輪 tool-command UI
walkthrough、external thesis experiment runner、MCP HTTP / long-running training tools 仍未完成，不能宣稱完整
release closure。
最新 UI-observable automated human-like walkthrough 已新增：
`scripts/dev/capture_human_like_product_walkthrough.py` 會用真 MainWindow / Data Interpretation
dialog / ChatPanel / ApplicationService capture `20` 張 screenshot、visible text snapshot、button
state、workflow state、CommandResult payload、tool transcript、user-facing transcript、recipe
artifact 和 process/thread notes。artifact
`artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` / `.md` 顯示 status `passed`、
`26 / 26` phases、human desktop acceptance `not performed`。最新 artifact 已補上 top-level
`observable_evidence` 和 `ui_quality_review`：`26` 個 phase 都有 visible text、button
state、workflow/backend snapshot index，`20` 張 screenshot 全部通過 nonblank check，visible text
raw tool / schema / traceback leakage check 為 `0` findings。後續 UI polish 已依截圖修正
Data Interpretation preview / confirm dialog 的 review surface density、Training plot dark-theme
readability、Training history compact header、Evaluation page compact controls，以及 ChatPanel
new conversation / reset 後的 stale bubble / stale workflow status，並刷新同一份
walkthrough artifact。這支撐 automated PyQt replay
條件下主要 UI path 可操作；仍不能替代 Windows Desktop 真人 click-through、雙螢幕 / DPI 或長時間
true local model desktop session。

## 可信狀態

- active repo：`/mnt/d/workspace_v2/projects/lab/XBrainLab`
- 舊 repo 副本：`/mnt/d/repos/XBrainLab`，目前只作 archive / reference。
- branch：`codex/stabilization-autopilot`
- remote：`https://github.com/hxin-an/XBrainLab.git`
- docs 已收斂成 `target/`、`architecture/`、`planning/`、`decisions/`、`validation/`、`records/`，根層只保留入口與目前狀態 / 操作文件。
- root `ROADMAP.md` 已刪除；目前路線只看 `docs/planning/roadmap.md`。
- `CHANGELOG.md` 只保留歷史版本紀錄，不作 current truth。
- 標準 Poetry env 已安裝 `dev,test,docs` dependency group：
  - `/home/administrator/.cache/pypoetry/virtualenvs/xbrainlab-TKrzxeIe-py3.12`
- import probe 已通過：
  - `PIL 12.1.0`
  - `mne 1.11.0`
  - `PyQt6`
  - `torch 2.11.0+cu130`
  - `pytest 8.4.2`
  - `XBrainLab 0.5.6`
- 文件站點已可用：
  - `poetry run mkdocs build --strict`
- local assistant runtime 已可用且受 first-run consent 控制：
  - primary：`microsoft/Phi-4-mini-instruct`
  - fallback：`microsoft/Phi-3.5-mini-instruct`
  - cache：`XBrainLab/llm/core/models`
  - current cache usage：約 `15.34 GB`
  - Qwen cache 已刪除；中國公司或中國來源模型不列入選型。
- 桌面 launcher 已產出：
  - repo source：`scripts/launchers/xbrainlab_wsl_launcher.cmd`
  - repo source：`scripts/launchers/xbrainlab_wsl_launcher.ps1`
  - Windows Desktop：`/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd`
  - automated walkthrough：`artifacts/launcher/windows-launcher-walkthrough.md`

## 品質門檻

最新 fast dashboard：

- generated at：`2026-05-04 04:07:48 UTC+08:00`
- workspace：`/mnt/d/workspace_v2/projects/lab/XBrainLab`
- overall：`PASS`
- 來源：`artifacts/quality/latest.json`、`artifacts/quality/latest.md`

當時全部 gate 都是 `PASS`：

- Ruff Lint
- Basedpyright
- Architecture Compliance
- Startup Smoke
- UI Baseline Capture
- UI Dialog Acceptance
- UI Unit Suite
- Real-Data IO Integration

最新 fast dashboard 摘要：

- Ruff Lint：`PASS`
- Basedpyright：`PASS`，`0 errors, 0 warnings, 0 notes`
- Architecture Compliance：`PASS`
- Startup Smoke：`PASS`
- UI Baseline Capture：`PASS`，`7 UI artifacts match approved references`
- UI Dialog Acceptance：`PASS`
- UI Unit Suite：`PASS`，`831 passed`
- Real-Data IO Integration：`PASS`，`31 passed, 8 warnings`

補充已知通過項目：

- supervisor final gates：
  - `git diff --check`
  - `poetry run ruff check .`
  - `poetry run basedpyright`
  - `poetry run mkdocs build --strict`
  - `poetry run python tests/architecture_compliance.py`
  - UI product / geometry gate：`121 passed`
  - agent / backend command gate：`225 passed`
  - backend + IO integration：`33 passed, 8 warnings`
  - full pipeline integration：`70 passed, 4 warnings`
  - LLM / local settings / script unit gate：`674 passed`
  - deterministic tool-call eval refreshed tracked `artifacts/agent_evals/latest.json`：
    commit `e5454c7 test: refresh agent eval artifact`
- backend Application Service / facade contract suite：
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `9 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
  - `44 passed`
- 2026-05-03 assistant UI + backend workflow contract gate：
  - `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run ruff check XBrainLab/ui/chat XBrainLab/ui/components/agent_manager.py XBrainLab/backend/application XBrainLab/backend/facade.py tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/integration/pipeline/test_public_cross_source_training_smoke.py tests/unit/backend/test_facade_headless.py`
  - `PASS`
  - `poetry run pytest --capture=sys tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_headless.py tests/integration/pipeline/test_public_cross_source_training_smoke.py -q`
  - `80 passed, 3 warnings`
- 2026-05-04 Data Interpretation backend command baseline gate：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py -q`
  - `28 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/integration/backend/test_application_service_workflow.py tests/integration/agent/test_tool_call_eval.py -q`
  - `92 passed`
  - `poetry run ruff check XBrainLab/backend/application tests/unit/backend/application/test_application_service.py scripts/agent/evals/run_tool_call_eval.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/backend/application scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_application_service.py`
  - `0 errors, 0 warnings, 0 notes`
  - broader static/docs gates:
    `poetry run ruff check .` -> `PASS`;
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`;
    `poetry run mkdocs build --strict` -> `PASS`
- UI unit suite：
  - latest fast dashboard UI Unit Suite：`831 passed`
- LLM unit suite：
  - `poetry run pytest --capture=sys tests/unit/llm -q`
  - `652 passed`
- agent tool/control suite：
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `321 passed`
- 2026-05-02 product delivery targeted gate：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q`
  - `62 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/tools/test_application_surface.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q`
  - `95 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - `31 passed, 8 warnings`
  - `timeout 600s poetry run pytest --capture=sys tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q`
  - `2 passed`
- backend unit suite：
  - `poetry run pytest --capture=sys tests/unit/backend -q`
  - `2661 passed, 1 skipped, 1 xfailed`
- backend + IO integration：
  - `poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
  - `33 passed`
- full pipeline integration：
  - `poetry run pytest --capture=sys tests/integration/pipeline -q`
  - `70 passed`
- local assistant runtime smoke：
  - preflight：
  - `poetry run python scripts/dev/plan_local_model_download.py --format markdown`
  - primary `microsoft/Phi-4-mini-instruct` already cached；estimated download `0.00 GB`；
    current / projected cache `15.34 GB`；available disk `158.54 GB`；VRAM estimate `9.0 GB`；
    license MIT
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
  - primary prompt smoke：`passed`
  - primary structured-output smoke：`passed`
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --model microsoft/Phi-3.5-mini-instruct --format markdown --prompt-smoke --structured-smoke`
  - fallback prompt smoke：`passed`
  - fallback structured-output smoke：`passed`
- startup smoke：
  - `timeout 45s xvfb-run -a poetry run python run.py --model local`
  - `MainWindow initialized` 後 timeout 結束，屬於 GUI smoke 預期結果。
- tool-call eval deterministic baseline：
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
  - artifacts：`artifacts/agent_evals/latest.json`、`artifacts/agent_evals/latest.md`
  - `21 / 21` cases passed；deterministic baseline，不是 local LLM performance claim。
- 2026-05-02 assistant runtime consent / query command / thesis protocol closure：
  - UI product gate：`62 passed`
  - backend / split audit / config gate：`41 passed`
  - agent / facade / backend workflow gate：`130 passed`
  - full test gate：`4386 passed, 3 skipped, 3 deselected, 1 xfailed, 14 warnings`
- `ai-assistant-open.png` 的 `(1684, 800)` product redesign baseline 已接受，尺寸和
  live artifact、repo HEAD reference 一致。
- 2026-05-02 final repair / closure commits：
  - `8b04380 ui: rebuild assistant sidebar product shell`
  - `1883d4b backend: complete command surface migration`
  - `8a6099a llm: enforce local-only assistant runtime`
  - `41ec91c docs: align local-only runtime status`
  - `3edee21 ui: clarify assistant unavailable and confirmations`
  - `5ed1c87 backend: route montage through command surface`
  - `4cd4d4c test: align agent manager local-only expectations`
  - `406719c ui: stabilize baseline capture geometry`
  - `e5454c7 test: refresh agent eval artifact`
- 2026-05-02 assistant product audit follow-up targeted evidence：
  - UI assistant / settings / AgentManager gate：
    `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
    - `131 passed`
  - agent product-flow / backend command gate：
    `timeout 240s poetry run pytest --capture=sys tests/integration/agent/test_product_flow.py tests/unit/llm/agent/test_controller.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/core/test_config.py -q`
    - `110 passed`
  - backend application / facade workflow gate：
    `timeout 240s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
    - `57 passed`
  - product walkthrough / agent integration：
    `tests/integration/ui/test_product_walkthrough.py` -> `2 passed`
    `tests/integration/agent/test_tool_call_eval.py tests/integration/agent/test_product_flow.py` -> `7 passed`
  - UI capture artifact：
    `artifacts/ui/ai-assistant-open.png`，已同步更新 approved baseline
    `tests/baselines/ui/ai-assistant-open.png`。

## 邊界與未驗證事項

- `docs/legacy/` 已整合後刪除。
- `docs/active/` 已收掉；canonical 文件直接放在 `docs/` 根層。
- `.agents/legacy/` 已整合後刪除；現行 agent 操作層只剩 `.agents/stack.md`、runbooks、context。
- 舊文件裡的 `/mnt/d/repos/XBrainLab` 絕對路徑不代表現在 active path。
- thesis / agent performance claim 不能只靠 engineering dashboard 支撐。
- local transformer runtime 已以 primary / fallback model smoke 驗證；4-bit / bitsandbytes
  仍是 optional path，不是預設產品依賴。
- agent runtime 目前是 local-only product path。`INFERENCE_MODE=api`、舊 settings 中的
  Gemini active mode、或 worker 直接要求 remote model，都會被 local migration / fail-closed
  guard 擋住，不會 instantiate remote backend。
- remote SDK 只留在 optional legacy dependency group；default dependency 不包含 OpenAI /
  Google Gemini SDK。
- thesis protocol 已建立 split artifact schema、split audit helper 和 validator script；正式
  external dataset runner、統計報告還沒完成。local LLM 真實 tool-call runner 已有
  primary / fallback `117` thesis-candidate cases x `3` repeat evidence，兩個 local model
  均為 `117 / 117` pass，並有 dashboard breakdown；這支撐 tool-call thesis-candidate
  benchmark，不支撐 UI / launcher 產品完成 claim。

## 目前 blocker / release risks

目前舊 final gate 判定已失效，不能用它宣稱 product delivery 完成。新的狀態是：

- AI Assistant 一般輸入 `hello` 曾出現 silent no-response；本輪已補 visible-response contract、
  deterministic product-flow test 和 product click-through smoke。
- ChatPanel 視覺曾偏 debug dock；本輪 follow-up 已把 top chip row、`Conversation` header、
  chat composer 底下狀態列和不存在的 mode/step controls 移除。第一層控制收斂到 dock
  title bar 的單一功能列，並用 regression tests 保護 disabled Retry、empty state、bubble
  minimum width、composer fit 和 raw tool output 不外洩。
- automated gate 漏掉了最基本的 user-visible chat product flow。deterministic eval `21 / 21`、
  local prompt smoke、launcher startup smoke 都不能替代真 chat flow 驗收；local tool-call
  eval runner 也不能替代 true ChatPanel multi-turn / tool-command walkthrough。
- UI import / preprocess / epoch / channel selection、split / model / training setting dialogs、
  evaluation / visualization / saliency query、training start-stop / reset、metadata update、
  smart parse、remove files、label import、montage confirmation 已有 service-backed command
  adapter；Start Training button 現在也會在 backend long-running capability 要求時顯示
  confirmation。mock / unit-test compatibility fallback 仍保留，但 real `Study` path 走
  `ApplicationService.execute()`。
- Agent mapped tools 的一批 path 已直接回 `CommandResult`；`load_data` 也已先做 directory
  expansion 再進 command surface，但不再出現在 Empty / Data Loaded / Preprocessed stage 的
  primary prompt；`attach_labels` 也已從這些 stage 的主工具語言移除。read-only
  `list_files` / `get_dataset_info` 會被正規化成 typed result。visible transcript 只顯示使用者語言；raw tool payload 保留在 diagnostics。
  `set_montage` 和 `switch_panel` 仍是 UI request path；真正 montage apply 在 confirmation
  後走 `ApplyMontageCommand`。
- 真 Windows launcher 尚未人工驗收；true local model ChatPanel 已有一般回覆 walkthrough、
  單步 `query_state` tool-command walkthrough、兩 turn workflow walkthrough artifact，以及
  Data Interpretation `scan_source` -> `preview_interpretation` -> `validate_interpretation`
  短鏈 tool-command artifact，並已有 confirm/apply -> standard preprocess -> epoch -> dataset
  pipeline-chain artifact、dataset-ready -> model / training settings / analysis-readiness
  boundary artifact，以及 controlled tiny training completion -> evaluation metrics ->
  saliency/visualization readiness artifact。MainWindow VisualizationPanel 也已有 post-training
  Saliency Map / Spectrogram / Topographic Map Matplotlib render artifact，且 headless 3D tab 會顯示
  blocked reason 不再 crash。這仍不是真人 Windows Desktop click-through，也不是 interactive
  desktop 3D / PyVista render 或 ChatPanel UI-routing render 的驗收。
- Windows/WSLg 雙螢幕開窗問題已用使用者回報的 offset screen geometry 補 regression；
  fallback policy 是 maximized，不是 fullscreen。但這仍不能取代真人桌面 click-through。
- `tests/integration/ui/test_product_walkthrough.py` 仍是 synthetic / patched training
  walkthrough，不是真正從 UI click 到 real TrainCommand completion 的產品 E2E。

仍存在的非阻塞架構風險：

- `evaluate` / `visualize` / `saliency` / `new_session` 已是 service-backed query / lifecycle
  command；`evaluate` / `visualize` / `saliency` 也已暴露成 ApplicationService-backed agent
  tools。它們目前回傳 summary / setup diagnostics，不等於完整互動式 analysis workflow 已完成。
- tool-call eval 已有 deterministic baseline 和 primary / fallback 真 local model runner；最新
  primary / fallback `117` thesis-candidate cases x `3` 都是 `117 / 117` pass，且 dashboard
  已列出 case family / metric / failure taxonomy / model comparison。這解除先前 `54` case 數不足、
  bandpass-vs-standard preprocess failure，以及只測乾淨英文 prompt 的 coverage gap。ChatPanel true local
  model one-turn、單步 tool-command、兩 turn workflow walkthrough、Data Interpretation
  短鏈 tool-command walkthrough 和 import-to-dataset pipeline-chain walkthrough 也已通過，
  但這些仍不能替代真人 Windows launcher click-through、training / evaluation / saliency 長鏈
  tool-command chain 或完整 UI import wizard 產品驗收。
- Data Interpretation backend command baseline、agent tool exposure、Dataset panel main
  import entry、recipe save option、headless/MCP-ready command schema、stdio MCP server
  baseline、deterministic eval cases、第一版 UI-observable replay artifact 和 wizard review
  hardening 已進入新心智模型；label import 目前仍是 service-backed compatibility UI，但成功結果
  已會寫入 Data Interpretation recipe trace；MCP/headless schema 已把 `load_data` /
  `attach_labels` / `import_labels` 標成 legacy compatibility 並指向 Data Interpretation preferred
  commands；MCP stdio external-client artifact 和 committed Inspector-style `mcp.json` release config baseline 已完成；MCP Inspector GUI click-through
  artifact 也已完成。HTTP transport 和 long-running training through MCP 尚未完成。

## 目前執行中

1. 繼續 backend architecture cleanup：`ApplicationService` 已拆出 Data Interpretation、
   Analysis、Training、Dataset Generation、Lifecycle、Data Compatibility 和 Data Table command
   services、Preprocess command service，以及 State / Query services；下一輪應檢查是否還有
   UI / agent / MCP 旁路或 wrapper compatibility 心智模型，而不是再把 workflow 塞回 service。
   Agent primary stage prompt 已先把 legacy `load_data / attach_labels` 降權，後續要繼續檢查
   UI 是否也完全以 Data Interpretation 作為新資料入口語言；MCP/headless schema 已先把
   legacy commands 標成非 primary workflow。
2. 等待真 Windows Desktop launcher click-through。
3. 補 interactive desktop 3D / PyVista render 或真人 blocked verification；不要把 offscreen blocked
   reason 或 Matplotlib 2D render 擴張成完整 visualization suite。
4. 修 mature import wizard 內嵌 label / anchor / MAT variable editor，讓 compatibility label
   import 不再是主要使用心智模型。
5. 繼續根據 human-like walkthrough screenshots 做 UI polish；第一輪已處理 Data Interpretation
   table density、Training plot readability / history header、Evaluation compact controls 和
   ChatPanel reset stale UI，仍要補 mature import wizard editing、assistant main-window narrow
   composition 和整體產品感。
6. 將 primary / fallback `117` case tool-call dashboard 整理成 thesis evidence report；不要把它
   擴張成 UI / launcher 完成 claim。
7. external EEG dataset experiment / statistical reporting 只作 pipeline support，不作 thesis
   主評分。

## 相關文件

- [target/README.md](target/README.md)
- [planning/now.md](planning/now.md)
- [operations.md](operations.md)
- [validation/README.md](validation/README.md)
