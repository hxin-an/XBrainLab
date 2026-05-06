# XBrainLab 目前狀態

最後更新：`2026-05-06`

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
偷偷載入大型模型。最新 local model downloader lifecycle cleanup 也讓下載 worker 在
finished / error / cancel 後 bounded join subprocess 並關閉 queue；AI Assistant settings dialog
關閉或取消時會走 bounded downloader shutdown，而不是只發 cancel 後直接銷毀 dialog。這是
明顯 thread/process cleanup smoke，不是長時間 local model soak。後續 local runtime shutdown
slice 又新增 `LocalBackend.unload()`、`LLMEngine.close()` 和 `AgentWorker.shutdown()`：controller
close 會 bounded 停止 generation thread、卸載 cached backend，並在可用時清 CUDA cache。這降低
assistant open/close 與 model switch 後的 GPU/cache 殘留風險，但仍不是長時間 true local model
桌面 soak。
同一輪 training lifecycle cleanup 也讓 `Trainer.clean(force_update=True)` 在中斷 training job
後 bounded join background thread；若 thread 未在 timeout 內停止會回錯並保留 trainer handle，
避免 `TrainingManager.clean_trainer()` 在 job 仍存活時把取消 handle 清掉。這是 thread lifecycle
guard，不是完整長時間 training soak。
最新 visualization cleanup 又補上 `Saliency3DPlotWidget.clear_plot()` 的 Qt widget teardown
guard：清空 3D plot 時會 detached child widgets、對非 plotter child 排程 `deleteLater()`，
並對 PyVista plotter 走 close / deleteLater 的 runtime-safe cleanup。這降低反覆切換 3D view
後留下 detached Qt/PyVista widget 的風險，但仍不是 interactive desktop 3D render、OpenGL
soak 或 Windows human desktop acceptance。
最新 plot-window cleanup 也讓 `SinglePlotWindow.closeEvent()` 關閉目前 `fig_param["fig"]`
所持有的 Matplotlib figure，並 detach / `deleteLater()` figure canvas 與 toolbar，再清掉引用。
這降低反覆開關 training / evaluation / visualization plot 視窗後留下 Matplotlib / Qt widget
reference 的風險，但仍不是完整 visualization soak 或桌面人工驗收。
最新 saliency 2D cleanup 又把 Map / Spectrogram / Topomap 的 figure replacement 收斂到
`BaseSaliencyView._replace_figure()`；替換或關閉 saliency view 時會 close 目前 figure、detach
canvas、排程 `deleteLater()` 並清引用。這降低反覆切 saliency view 後留下 Matplotlib canvas 的
風險，但仍不是完整 saliency workflow UX 或長時間 visualization memory soak。
最新 evaluation cleanup 也讓 `ConfusionMatrixWidget.update_plot()` / close path 會 close 目前
Matplotlib figure、detach / `deleteLater()` 舊 canvas 或 message widgets，並清掉 canvas /
figure 引用。這降低 Evaluation tab 反覆切 plan / 清空資料時留下舊 widget 的風險，但仍不是
完整 evaluation UI soak。
最新 MetricsBarChart cleanup 也讓 per-class metrics chart close path close 目前 Matplotlib
figure、detach / `deleteLater()` canvas 並清掉引用；這補齊 Evaluation tab 另一個 Matplotlib
widget 的 focused close cleanup，但仍不是長時間 Evaluation memory trend proof。

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
baseline。最新 MCP boundary slice 又把 `tools/call` structured result 補上 adapter metadata：
`mode=headless_mcp_stdio`、stable `session_id`、`transport=stdio`、`ui_refresh.supported=False`；
stdio walkthrough Markdown 也會顯示這個 headless session boundary。最新 hardening 進一步讓 stdio
MCP 對 `train` 先尊重 backend capability / precondition：資料、dataset、model 或 training
option 尚未 ready 時會回「Generate datasets before training」這類 readiness reason，不會被
`long_running_job_required` 遮掉；只有 capability 已 enabled 的 long-running `train` 才回
`long_running_job_required`，明確表示 stdio 不同步執行長任務；HTTP train job status / cancel
則由後續 HTTP adapter baseline 承接。最新 HTTP transport baseline 已新增：
`XBrainLab.mcp.http_server` / `scripts/dev/run_mcp_http_server.py` 提供 local-only
`POST /mcp` JSON-RPC 和 `GET /health`，`MCPServer(transport="http")` structured result 會標示
`mode=headless_mcp_http`、`transport=http`、stable `session_id` 和 `ui_refresh.supported=False`。
`scripts/dev/capture_mcp_http_walkthrough.py` 會用 Python standard-library HTTP client 跑
health / initialize / tools/list / scan_source / preview_interpretation / train job / job status /
cancel，並保存 `artifacts/mcp/http-walkthrough.json` / `.md`；同 artifact 也確認
backend-ready long-running `train` over HTTP 會建立 `mcp-http-job-*`、可用 `GET /jobs/{id}`
查狀態，也可用 `GET /jobs` 在同一 session 內重新列出 jobs，並可用
`POST /jobs/{id}/cancel` 透過 `StopTrainingCommand` 取消。HTTP registry 也已補同 session
duplicate-start guard：第一個 train job 還在 start boundary 內或 running 時，第二個 `train`
會回 `job_already_running` structured blocked result，不會啟動第二次 training；已 cancelled /
completed 的 HTTP job snapshot 也會保存 terminal status，不會被後續新 run 的全域 training state
改寫。這是 in-memory headless HTTP train job baseline；仍不是 evaluation / visualization job API、
job persistence / recovery、multi-client recovery-grade resource lock、remote authorization
certification、Windows human launcher acceptance 或 full MCP client certification。後續 hardening slice 又讓 HTTP adapter
用 constant-time Bearer token compare，並用 bounded request body size 拒絕過大 JSON-RPC body；
這是 local adapter abuse guard，不是 remote security certification。最新 MCP schema slice 也把
capability-derived `execution` boundary 放進 `tools/list` `x_xbrainlab` metadata：外部 client
可直接看到 `long_running`、`destructive`、`requires_confirmation`、`decision_boundary`、
`requires_http_job` 和 `supported_job_transports`；目前 `evaluate` / `visualize` / `saliency`
仍是 immediate typed ApplicationService result，不是 HTTP job API。另已新增 non-mocked backend
workflow evidence：synthetic FIF source 會走 scan -> preview -> validate ->
confirmation-blocked apply -> confirmed apply -> save recipe -> reload recipe review ->
preprocess -> epoch -> dataset，並檢查 split audit / train-val-test counts。UI-observable
replay 也有第一份 artifact：`scripts/dev/capture_data_interpretation_replay.py` 會保存
`artifacts/ui/data-interpretation-preview.png`、`data-interpretation-applied.png` 和
`data-interpretation-replay.json`，對照 visible dialog state、dataset panel state 和 command
result。最新 replay JSON 也保存表格幾何 evidence：Dataset table 與 preview/remap dialog 的
metadata、label carriers、event roles、Review Summary tables 都有 `header_length`、
`viewport_width`、`column_widths`、`horizontal_scrollbar_max` 和 `text_elide_mode`，可重跑確認欄位填滿
容器且沒有水平外溢。最新 geometry evidence 又對 Dataset table 增加 `widget_width`、
`panel_width`、`table_right_x`、`right_boundary_x` 和 `right_gap_to_boundary`，確認載入資料後
table 會貼齊 sidebar 邊界而不是只讓欄位填滿一個內縮 viewport。最新 replay-level gate 也會在
`ui_quality_review.geometry` 檢查 preview / remap wizard 的 metadata、label/event、Review
Summary tables 和 Dataset table；若出現水平 overflow、underfill 或半截 visible row，replay
script 會 fail，而不是只把問題藏在 screenshot 裡。Data Interpretation preview dialog 已硬化成第一版 import wizard review surface：
可見 `Select source | Scan result | Preview | Confirm | Apply | Save recipe` 流程、source/readiness、
BIDS status、metadata preview、label/event/recipe trace、confirmation 和 recipe save 選項；最新 UI
polish 已把 warning / confirmation / downstream impact / format boundary 從大段文字框改成
`Review Summary` 表格，artifact 會保存 `review_summary_rows`，避免使用者面對 raw review dump；
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
需要的 `seconds`、`trial`、`class cue labels`。最新 UI selector slice 又把 event role rows
從 free-text edit 收斂成 `QComboBox` selector；`trial_type` 會以 `Class cue` 這類人話顯示，
artifact 也新增 `event_rows`，但 recipe choices 仍保存 `class cue` 等 backend values。最新
event display polish 又把 visible event-role item 從 `label_carrier` / `trial_type` 這類 source /
internal key 改成人話 `Label carrier` / `Trial type`，backend choices 仍保存原 key；label /
event 區塊標題也改成 `Label and Event Interpretation`，recipe trace 留在 `Review Summary`。最新
wizard polish 又把 label carrier selector 顯示從 raw `trial_type` / `onset` 類 source keys 改成
`Trial type` / `Onset` 等人話 label，並把 `Review Summary` alternate row 再降到更克制的
dark-theme contrast；後續欄位權重 polish 又加寬 label-carrier `Format` 欄，讓 `BIDS events`
這類常見格式名稱在 product-width dialog 中完整可見；latest selector-fit follow-up 又調整
Matched EEG / Time / Granularity / Role 欄位權重，讓 `Needs review` 和 role selector 不再被截成
`Needs re`；BIDS target file 在 table 內以 `sub-01 run-2` 這種 compact label 顯示，但 recipe
choices / apply diagnostics 仍保存完整 `sub-01_task-mi_run-2_raw.fif`。最新
decision-copy slice 又把 wizard 頂部狀態從 `Validation needs confirmation...` 改成使用者語言
`Review and confirm these choices before applying.` / `Ready to apply.` / replacement-file guidance；
artifact visible text 已刷新。後續 slice 又新增 format capability
boundaries：scan / preview 會列出 GDF、EDF / BDF、EEGLAB、BrainVision、MNE FIF、MAT labels、
CSV / TSV / BIDS events、TXT labels 和 XDF / LSL 的 supported / needs-review / blocked 邊界；
dialog `Review Summary` 會用人話顯示這些邊界，XDF / LSL 目前會明確提示 stream selection
尚未在 wizard 內可用。後續 slice 已新增 generated format capability matrix artifact：
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
看到不同資料入口真相。最新 recipe reload slice 修正了 saved recipe rehydration：`ReloadInterpretationRecipeCommand`
現在會把 recipe 裡的 selected EEG files、metadata overrides、label carrier choices、event roles
和 class map 轉回 candidate `choices` 後再 preview / validate。human-like walkthrough artifact
的 reload command result 現在可見 `choices:metadata_overrides` / `choices:event_roles` /
`choices:label_carriers` recipe trace；`07-recipe-reloaded.png` 現在是 reload preview dialog，
phase notes 也保存 `Reloaded recipe / Reapplied` review row。這支撐 reload 不是只讀 source
path 的空 preview，且使用者可在 wizard 看到 saved choices 已重新套用。它仍不是完整 recipe
diff UI。
最新 backend architecture cleanup 又把 Data Interpretation lifecycle
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
最新 legacy-loader boundary slice 又把 `DatasetPanel.apply_loader()` 隔離成 mock / legacy-only
adapter；real `Study` runtime 會拒絕 direct `loader.apply(study)`，提示使用
Data Interpretation workflow，且 architecture compliance 會阻止新的 UI direct loader apply 旁路。
下一個 UI cleanup slice 又把 Training sidebar 的 destructive cleanup path 收回 command spine：
重新 split 前清 datasets 走 `ClearDatasetsCommand(confirmed=True)`；Clear History 會先要求
使用者確認，再走 `ClearTrainingHistoryCommand(confirmed=True)`，successful service result 不再
落回 controller mutation。
最新 UI autonomy slice 讓 Training sidebar 的 `Start Training` button 也尊重 backend
`train` long-running boundary：當 capability 顯示需要 confirmation 時，UI 會先用使用者語言詢問
是否開始可能耗時且使用 CPU/GPU 的訓練；拒絕時不會執行 `TrainCommand`，service 成功時不再
fallback 到 controller。Automated Qt replay artifact 在
`artifacts/ui/training-start-confirmation/`，它不是 human desktop acceptance。
最新 backend command-gate cleanup 把這條 boundary 下沉到 Command API：`TrainCommand` 現在
有 `confirmed` 欄位，`XBrainLab/backend/application/command_gate.py` 會先檢查 capability
blocked reason，再統一檢查 `confirmation_required` / `requires_confirmation`。因此 unready
training 仍回「Generate datasets before training」這類 precondition；backend-ready 但未 confirmed
的 `train` 會被 `confirmation_required` 擋下，不會只靠 UI/agent 外層自律。
Data Interpretation backend boundary cleanup 已把原本集中在大型 domain module 的責任拆到
focused modules：format capability taxonomy 在 `data_interpretation_formats.py`，metadata /
BIDS / recipe rehydration 在 `data_interpretation_metadata.py`，recipe serialization 在
`data_interpretation_recipe.py`，label carrier planning 在
`data_interpretation_label_carriers.py`，preview / validation review 在
`data_interpretation_review.py`，source scanner 在 `data_interpretation_scan.py`，candidate
builder / metadata override 在 `data_interpretation_candidate.py`，session stores / latest-id /
snapshot assembly 在 `data_interpretation_state.py`。`data_interpretation.py` 目前只保留 shared
decision enum、`AppliedInterpretation` 和 public compatibility re-exports；`DataInterpretationCommandService`
主要保留 command handler orchestration，不再同時承接 state truth。這是 backend internal
boundary cleanup，不是 mature import wizard completion。
最新 Data Interpretation UI source-entry slice 讓 Dataset sidebar 明確提供三個資料入口：
`Interpret Data Source`（EEG file(s)）、`Interpret Folder / BIDS` 和 `Reload Import Recipe`。
folder/BIDS root 與 recipe reload 都走 Data Interpretation command path；UI-observable artifact 在
`artifacts/ui/data-source-entry-options/`。這補上 source type entry visibility，但不是 mature
embedded label editor completion。後續小修又讓 recipe reload 讀自己的
`reload_interpretation_recipe` capability gate，而不是共用 `scan_source` gate。
最新 backend capability hardening 讓 `apply_interpretation` 也套用 raw-edit blockers：active
session 已有 epoch、generated dataset、trainer 或 locked raw data 時，UI / agent / MCP 都會收到
reset/new-session blocked reason，而不是直接把新 interpretation 套進既有 downstream pipeline。
最新 agent tool-surface cleanup 把舊 `load_data` / `attach_labels` 從 Empty / Data Loaded /
Preprocessed stage prompt 和 primary tool exposure 移除；Context Assembler 會把 backend
capability policy 與 stage allowlist 取交集，避免 backend compatibility policy 把已降權的
legacy tool 重新塞回主 prompt。`load_data` / `attach_labels` 仍在 schema taxonomy、parser /
verification 和 `DataCompatibilityCommandService` 作為 legacy compatibility surface，但新
agent 心智模型已改以 Data Interpretation scan / preview / validate / apply / recipe 為資料入口。
最新 RAG prompt cleanup 又把 bundled gold-set / BM25 / dense retrieval 都接上同一個
primary-workflow policy：含 `load_data`、`attach_labels` 或 `import_labels` 的 examples 不會
被新 indexer 建入，也會在 retriever formatting 前被過濾，避免已存在的舊 local Qdrant
collection 把 legacy few-shot examples 注入 prompt。
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
flow 的使用者語意；最新 target-selection cleanup 也讓 selected/all-row target files 直接來自
Dataset table row 的 `UserRole` data，不再為了開 dialog 回讀 stale
`DatasetController.get_loaded_data_list()`。最新 target fallback boundary 也讓 real `Study`
若 table row 缺少 `UserRole` data 會 block 並要求刷新 workflow，不再 fallback 到 controller
loaded list。後續 guard slice 已讓 `Add Labels to Loaded Data` 在沒有 loaded data 時 disabled，
tooltip 引導使用者先 interpret data source，且 action 會尊重 backend
`ImportLabelsCommand` capability block。UI replay JSON 也保存 empty-state disabled button 和
applied-state enabled recipe-trace tooltip。最新 event-filter suggestion cleanup 也讓 label import
的 smart event filter 先走 `QueryStateCommand(query="smart_filter_suggestions")`，不再在 real
`Study` path 直接回讀 `DatasetController.get_smart_filter_suggestions()`；service unavailable 時
只略過建議選取，legacy controller suggestion 只留給 explicit mock / legacy fallback。最新 UI capability slice 又讓 real Study 的 Dataset
sidebar 直接讀 backend `import_labels` 和 `preprocess` capability：button disabled state /
tooltip 和 Channel Selection preflight 不再只靠 controller-local `has_data` / lock 判斷。latest
label compatibility wording cleanup 也把 target-selection dialog / warning title 從
`Import Label` 改成 `Add Labels to Loaded Data` / `Add Labels Blocked`，避免 compatibility UI
把使用者帶回舊 Import Label 心智模型。latest
follow-up 也把 Channel Selection 的 controller-local `has_data` / `is_locked` checks 限縮到
mock / legacy path；real `Study` path 以 backend `preprocess` capability 為準。最新 follow-up
又讓 Channel Selection dialog 的 loaded data list 先走
`QueryStateCommand(query="data_lists", include_objects=True)`；`DatasetController.get_loaded_data_list()`
只留在 no-capability mock / legacy path。最新 query-unavailable fallback boundary 也讓 real
`Study` 若 query helper 意外回 `None`，會 block Channel Selection 並顯示 shared safety
message，而不是開 stale controller-backed dialog。最新 destructive-action polish 也讓 real
`Study` Dataset sidebar 的 `Clear Dataset` availability 讀
`QueryStateCommand(query="state")`：empty dataset / reset 後 disabled 且 tooltip 顯示
`No dataset to clear.`，只有 raw / preprocess / epoch / dataset / training / evaluation /
applied interpretation state 存在時才 enabled；直接呼叫 empty clear action 也只顯示人話
notice，不會進入 reset confirmation。disabled success / danger / warning action tokens 也改成
中性灰色，避免 disabled destructive button 仍像可按。它仍
不是完整 Data Interpretation 內嵌 label editor。後續 Smart Parse capability slice 也讓
`open_smart_parser()` 在 real Study path 先讀 backend `apply_smart_parse` capability；沒有 raw data
時不會打開 parser dialog，而會顯示 shared blocked reason。latest follow-up 也把 Smart Parse
的 controller-local locked / has-data checks 限縮到 mock / legacy path；real `Study` path 以
backend capability 為準，不再被 stale controller 狀態擋掉。latest Data Interpretation source
entry cleanup 也把 main file import 和 folder/BIDS source import 的 controller-local
`is_locked()` check 限縮到 mock / legacy path；real `Study` path 以 backend `scan_source`
capability 為準，不再讓 stale controller lock 擋住資料入口。後續 remove-files preflight 也讓
context-menu remove 在 backend `remove_files` capability disabled 時先顯示 shared blocked
reason，不再先要求使用者確認不可執行的 raw-data mutation。後續 batch metadata preflight 同樣
改讀 backend `update_metadata` capability，blocked 時不再先開 subject/session input dialog。recipe
save path 也已改成先讀 backend `save_interpretation_recipe` capability；blocked 時不會先開檔案
儲存對話框，label-import recipe trace 更新也不會提出無法成立的「現在儲存」確認。舊
`load_data / attach_labels` 仍不能宣稱已完全退出產品心智模型。

Preprocess sidebar 的 shared `check_lock()` / `check_data_loaded()` helpers 也已改成 real
`Study` path 先以 backend `preprocess` capability 為準；controller-local `is_epoched()` /
`has_data()` checks 只保留給 mock / legacy non-Study path。這避免 stale controller state 擋住
backend 已允許的 filter / resample / rereference / normalize / epoching 入口。
Dataset sidebar visible state 也已補齊：main source import、folder/BIDS import、recipe reload
和 Smart Parse button tooltip/enabled state 會讀 backend `scan_source`、
`reload_interpretation_recipe`、`apply_smart_parse` capabilities；real `Study` path 不再顯示 stale
controller lock 文案或讓 backend-blocked Smart Parse 看起來可點。Data Interpretation replay
artifact 也已刷新，`artifacts/ui/data-interpretation-replay.json` 現在保存 empty/applied Dataset
sidebar 全部 source / label / smart parse / channel selection / clear buttons 的 text、enabled 和
tooltip。
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
import wizard 或 MCP HTTP long-running job workflow 驗收完成。最新 tool-call
best-practices slice 又把 prompt-facing schema、no-call / clarification policy、nested schema
verification、parser / normalizer repair 和 scoring dashboard 對齊 OpenAI Structured Outputs、
BFCL 與 LangSmith trajectory-eval 設計；2026-05-05 follow-up 把 eval 擴到 `118` cases，
新增「已有 epoch/downstream lock 時，使用者要求套用
新 Data Interpretation 不可改叫 scan 或其他替代工具硬推」的 wrong-tool temptation case。後續
strict local rerun 也已用同一 `118` cases 跑 primary / fallback 各 `3` 次：
`microsoft/Phi-4-mini-instruct` 和 `microsoft/Phi-3.5-mini-instruct` 都是 `118 / 118`，
dashboard 已刷新。這輪同時修正 scorer，不再把 blocked intent 下的替代 tool
（例如 reset / scan / configure）誤算成 pass；direct blocked command 只算 verifier-blocked
response，不算已執行。後續 recipe remap schema follow-up 又把 deterministic suite 擴到
`121` cases，新增 recipe reload `eeg_file_remap`、`label_carrier_remap` 和 missing remap
target clarification；local primary / fallback 已用 cached non-China local models 各重跑 `3`
次，primary `microsoft/Phi-4-mini-instruct` 和 fallback `microsoft/Phi-3.5-mini-instruct`
都是 `121 / 121`，dashboard 已刷新。這支撐目前 remap-expanded benchmark slice；仍不等於
UI usability、Windows launcher、雙螢幕 / DPI、長時間桌面 session 或 product completion。最新
agent mapped-tool command boundary hardening 後也已完成同一 `121` case release / thesis gate
rerun；fallback full x3 在 RTX 5070 Ti 16GB 上觀察到 high resource pressure（約 `15764 MiB`
VRAM used、`232 MiB` free、fallback wall time 約 `41 min`），resource artifact 在
`artifacts/agent_evals/local-eval-resource-pressure-2026-05-05.*`。後續 tool-call eval 必須分層：
fast dev gate 跑 deterministic changed / failed cases、repeat `1`、不跑 fallback；candidate gate
只跑 primary affected families；只有正式 release / thesis claim 才跑 full deterministic +
primary x3 + fallback x3 dashboard。最新 CLI guard 也已讓
`scripts/agent/evals/run_local_tool_call_eval.py` 在啟動 local model 前寫入 disk / cache /
`nvidia-smi` VRAM preflight；full-suite repeat `3` local run 也必須顯式帶
`--eval-gate release` 或 `--eval-gate thesis`。若 CLI 留在預設 candidate gate，或正式 full
local gate 偵測到 high VRAM pressure，會先寫 `resource_preflight.json` / `.md` 並拒絕啟動
local model，避免 routine slice 誤跑 full fallback x3。日常 UI refresh、verifier、normalizer、
prompt 或 case wording 切片只應跑 fast dev gate；除非正在更新正式 release / thesis benchmark
claim，不應啟動 fallback full x3。最新 fast changed-case slice 又新增中文 label-action
missing-input case：`zh-label-action-missing-input` 會把「幫我貼標籤」判成需要 clarification，
deterministic source suite 因此變成 `122` cases；只跑
`artifacts/agent_evals/deterministic_changed/latest.*` 的 `1 / 1` changed-case gate，沒有重跑
local primary / fallback，也沒有更新正式 release / thesis benchmark claim。正式可引用的
primary / fallback x3 evidence 仍是上一輪同一 `121` case suite；若要宣稱 `122` case suite，
必須走 release / thesis gate 並先做 disk / cache / VRAM preflight。後續
ChatPanel local-model UI
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
MCP HTTP long-running job workflow 或成熟 import wizard label editor 完成。同 slice 修正了 saliency `method` /
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
click-through、MCP HTTP long-running job workflow 或成熟 import wizard label editor 完成。後續 runtime probe
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
walkthrough、external thesis experiment runner、MCP HTTP long-running training jobs 仍未完成，不能宣稱完整
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
raw tool / schema / traceback / selected internal snake_case command and recipe trace token leakage check 為 `0` findings；latest ChatPanel evidence hardening
also makes the visible text snapshots include chat bubble `QTextBrowser` content, so clarification /
blocked / successful assistant screenshots now have matching JSON text evidence and
`chatpanel.visible_messages` is populated before reset. 最新 table geometry review 會檢查
Dataset table 與 Data Interpretation wizard tree table 的 header / viewport / scrollbar、
right-boundary gap 和 clipped visible row 狀態，目前 `15` 個 table/tree widgets 全部通過、
`0` geometry findings、`0` clipped-row findings。最新 resource smoke gate 也會讓
walkthrough 在 close 後 Python threads 未回落、Qt thread pool 仍 active 或 RSS high-water delta
超過 threshold 時 fail；目前 artifact 顯示 resource smoke `passed=True`、RSS growth
`231556 KB` / limit `600000 KB`、Qt active thread `0`。最新 2026-05-06 artifact
也已刷新 Data Interpretation decision copy 和 ChatPanel composer placeholder，可見
`Review and confirm these choices before applying.` 以及 `Ask about EEG workflow`。這是 coarse cleanup smoke，不是
memory-leak proof 或長時間 soak。後續 UI polish 已依截圖修正
Data Interpretation preview / confirm dialog 的 review surface density、Training plot dark-theme
readability、Training history compact header、Evaluation page compact controls，以及 ChatPanel
new conversation / reset 後的 stale bubble / stale workflow status，並把 ChatPanel empty-state
next step 從 legacy `load_data` / `attach_labels` visible language 收斂成 Data Interpretation
`Scan data source` 主線；legacy compatibility tool fallback labels 也改成較中性的
`Import data` / `Add labels to loaded data`，避免 assistant summary 回到舊主流程語言。已刷新同一份
walkthrough artifact。最新 Dataset / Data Interpretation UI follow-up 又修掉 preview dialog
的 label / event / recipe trace table overflow、`Review Summary` 高對比黑白條紋，以及 Dataset
table 載入後欄位內縮問題：Dataset table 仍保留 interactive resize mode，但會依 viewport
等比例縮放所有欄位，讓欄寬合計貼齊主 panel，不再只把剩餘寬度塞進單一欄或在窄 panel
外溢；Data Interpretation preview / remap dialog 也會在顯示後用實際 viewport 重算 metadata、
label/event 和 `Review Summary` 欄寬。`Events` 欄現在用 `Events (n)` / `Labels (n)`
區分內建 events 與外部 labels，不再用綠色把 external labels 包裝成成功狀態。
最新 confirmation-copy polish 又把 preview dialog 底部從 raw confirmation item 串接長句改成
短 action cue：`Review the items marked Needs confirmation, then confirm and apply.`；具體的
metadata / label carrier confirmation 仍只放在 `Review Summary` table，避免底部重複 raw
filename。Data Interpretation replay
JSON 已保存 Dataset table headers、rows、resize modes 和 column widths，applied artifact
顯示全部欄位填滿主 panel；human-like walkthrough JSON 也同步保存同類 geometry evidence，
最新 capture geometry settling 會等 MainWindow startup recovery timer 跑完後再回到
`1280x800` artifact 尺寸，避免 automated replay 被 offscreen startup clamp 縮成窄視窗。
最新載入後 Dataset table artifact 顯示 `widget_width=1020`、`header_length=993`、
`viewport_width=994`、`right_boundary_x=1020`、`right_gap_to_boundary=0`、
`horizontal_scrollbar_max=0`，欄位填滿 sidebar 前的主 panel。最新 review-row polish 又讓 preview / remap dialog 的
`Review Summary` 高度對齊完整 row，JSON 現在保存 `vertical_scrollbar_max` 和
`partial_visible_rows`；最新 Data Interpretation replay 顯示 preview `Review Summary`
`partial_visible_rows=[]`、`vertical_scrollbar_max=4`，remap dialog `partial_visible_rows=[]`。
最新 selector-fit replay 也顯示 label carrier row 為 `events.tsv | sub-01 run-2 | BIDS events |
Trial type | Onset | Seconds | Trial | Class cue labels`，而 `review_choices` /
`label_apply.file_mapping` 仍使用完整 target filename。
最新 class-map preview slice 又讓 BIDS events / CSV / TSV label carrier 在未提供 explicit
`choices.class_map` 時，從已選 label 欄位擷取去重後的 observed label values，作為 wizard 可審查
class map row；artifact 顯示 `left` / `right` class map rows，且未修改時不會把它記成
`choices:class_map`。最新 BIDS sidecar UI replay follow-up 也把 same-directory
`events.json` 的 `trial_type.Levels` 納入 synthetic fixture，artifact 現在顯示 `Left hand` /
`Right hand` 這類 user-facing class labels；未編輯的 sidecar default 仍不會寫成
`choices:class_map`，找不到 sidecar 時則 fallback 到 observed value。
MAT follow-up 也支援基本 numeric MAT label variable preview，會把 `classlabel=[1, 2, ...]`
顯示成 `1` / `2` class map defaults，並跳過 NaN / struct / cell-like payload。這是
preview/default review support，不是 silent safe guess；label carrier 仍保持 `needs_confirmation`，
完整 BIDS inheritance certification、MAT 複雜 anchor reconciliation、raw trigger selector 和 full
embedded label editor 仍未完成。
最新 recipe-trace wording polish 又讓 `Review Summary` 不再把 `scan:scan-1`、
`choices:metadata_overrides`、`label_import:timestamp:1` 這類 backend trace token 直接顯示給使用者；
dialog 會顯示 `Source scan`、`Metadata choices`、`Label import` 等人話 rows，原始 recipe trace
仍保留在 backend state / JSON artifact 作為 diagnostics。這改善可讀性，但不等於 mature recipe
diff editor 或 final import wizard 完成。
最新 replay evidence guard 也把這件事納入 `data-interpretation-replay.json`：
`ui_quality_review.visible_text` 現在會檢查可見 replay text 是否含 raw command names 或 recipe
trace tokens；目前 artifact 顯示 `passed=true`、`findings=[]`。這只檢查 replay 捕捉到的 UI text，
不取代人工 Windows desktop review。
最新 human-like walkthrough visible-text guard 也擴充到 recipe trace tokens；artifact
`visible_text_boundary` 現在明確列出 raw tool syntax、schema、traceback、selected snake_case
command leakage 和 recipe trace tokens，且 `forbidden_visible_text=[]`。這仍只代表 captured UI
text，不能取代人眼設計審查。
同一 `partial_visible_rows` evidence 也已進入 consolidated human-like walkthrough 的 top-level
UI quality gate；未來任一被 capture 的 table/tree widget 出現半截 visible row，artifact 會 failed，
不會只靠人工目視偶然發現。
最新 Dataset sidebar polish 又修掉 `Aggregate Information` summary table 的最後一列裁切：
row height / panel height 已收斂成 13 列完整顯示，`Classes` 不再半截可見；human-like walkthrough
的 geometry review 也已把 `aggregate_info` table 納入檢查。
最新 consolidated walkthrough refresh 也重用 Data Interpretation replay 的 BIDS `events.json`
Levels fixture；`04-interpretation-preview.png` / `05-interpretation-confirm.png` /
`07-recipe-reloaded.png` 和 JSON 現在顯示 `Left hand` / `Right hand` class-map rows。Raw
`choices:class_map` 仍可能留在 backend command-result diagnostics 內供 recipe reload trace 使用，
但 visible-text guard 仍通過，代表這不是使用者可見 UI 文案。
最新 eval dashboard walkthrough screenshot 也已從 raw Markdown / pipe-table preview 改成
dark product-style report：model comparison、metric pass rates 等 section 以 styled tables 呈現，
並在第一屏提升顯示 Thesis Claim Boundary，避免先看到 100% 分數就誤讀成 product complete。
這只是 artifact presentation polish；本切片沒有刷新 deterministic 或 local model score，也不改變
release / thesis claim。
這支撐 automated PyQt replay
條件下主要 UI path 可操作；仍不能替代 Windows Desktop 真人 click-through、雙螢幕 / DPI 或長時間
true local model desktop session。
最新 recipe reload review slice 又把 saved recipe 與重新 scan 的 comparison 補進 preview
payload 和 wizard `Review Summary`：reload dialog 現在會顯示 `EEG files`、`Label carriers`、
`Saved choices` 這類 matched / changed rows，而不是只說 choices reapplied。`07-recipe-reloaded.png`
和 human-like walkthrough JSON 已刷新。這支撐 recipe reload UI 明確顯示差異的 automated
evidence；仍不是完整 recipe diff editor 或 human desktop acceptance。
同一 recipe reload 安全邊界後續又補上 missing saved EEG file blocker：若 recipe 的
`selected_eeg_files` 在重新 scan 結果中找不到，candidate validation 會變成 `blocked`，並用
`Selected EEG file(s) were not found in the current scan: ...` 這類人話 reason 擋在 apply
前，不再等到 import runtime failure。
同一 blocker pattern 也已套到 saved label/event carrier：recipe reload 會把 saved
`label_carriers` / `label_carrier_plan.path` 帶回 candidate choices，若 current scan 找不到對應
carrier，validation 會以 `Saved label/event carrier(s) were not found in the current scan: ...`
擋下，避免 recipe replay 靜默丟失 external labels。
後續 remap slice 已允許明確 `eeg_file_remap` / `label_carrier_remap`，可把 saved EEG file 或
saved carrier path/name 映射到 current scan 的 replacement；原 recipe 的 metadata override、
label field、anchor、time model、granularity 和 role choices 會套到 replacement。最新 UI slice
已把 wizard remap selector 接上：blocked reload dialog 會優先顯示 EEG file / label carrier
replacement selector，使用者選完後按 `Apply Remap`，UI 會 re-preview / re-validate 再 apply。
後續 agent/headless schema slice 已把同一個 preview choices schema 抽成
`data_interpretation_choice_schema.py`，讓 agent tool definition、headless
`command_specs()` 和 MCP `tools/list` 都可見 `choices.eeg_file_remap` /
`choices.label_carrier_remap`，並把 deterministic tool-call suite 擴到 `121` cases，新增
recipe reload remap、label carrier remap 和 missing remap target clarification。local
primary / fallback x3 也已針對同一 `121` case suite 重跑並更新 dashboard。這仍不是完整
conflict editor、複雜 anchor reconciliation，也不能替代 UI / launcher / import wizard 產品驗收。

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
  primary / fallback `121` thesis-candidate cases x `3` repeat evidence，兩個 local model
  均為 `121 / 121` pass，並有 dashboard breakdown。這支撐已重跑 tool-call benchmark slice，
  不支撐 UI / launcher 產品完成 claim。

## 目前 blocker / release risks

目前舊 final gate 判定已失效，不能用它宣稱 product delivery 完成。新的狀態是：

- AI Assistant 一般輸入 `hello` 曾出現 silent no-response；本輪已補 visible-response contract、
  deterministic product-flow test 和 product click-through smoke。
- ChatPanel 視覺曾偏 debug dock；本輪 follow-up 已把 top chip row、`Conversation` header、
  chat composer 底下狀態列和不存在的 mode/step controls 移除。第一層控制收斂到 dock
  title bar 的單一功能列，並用 regression tests 保護 disabled Retry、empty state、bubble
  minimum width、composer fit 和 raw tool output 不外洩。
- 最新 ChatPanel backend-status cleanup 讓 `AgentManager.refresh_backend_status()` 對不完整
  capability snapshot fail soft：缺少 `train` 或 candidate capability 時會把該 action 視為
  unavailable，而不是讓 assistant footer 掉成 `Workflow status unavailable`。
- 最新 ChatPanel data-entry wording follow-up 又把 no-data / no-action footer fallback 從
  `Import files to begin` 改成 `Scan a data source to begin`，避免在 capability snapshot 缺漏時
  把使用者帶回舊 data-entry 心智模型。後續 empty-state wording cleanup 也把 ChatPanel 初始
  guidance 裡的 `Import EEG files` 改成 `Scan a data source`。
- automated gate 漏掉了最基本的 user-visible chat product flow。deterministic eval `21 / 21`、
  local prompt smoke、launcher startup smoke 都不能替代真 chat flow 驗收；local tool-call
  eval runner 也不能替代 true ChatPanel multi-turn / tool-command walkthrough。
- UI import / preprocess / epoch / channel selection、split / model / training setting dialogs、
  evaluation / visualization / saliency query / settings gate、training data-splitting / configuration dialogs / start-stop capability /
  clear-history、reset preprocess / clear-dataset session、metadata update / inline editability、smart parse、remove files、label import、recipe save、AgentManager / Visualization sidebar montage blocked
  preflight / confirmation 已有 service-backed command adapter；Start Training button 現在也會在 backend long-running capability 要求時顯示
  confirmation。mock / unit-test compatibility fallback 仍保留，但 real `Study` path 走
  `ApplicationService.execute()`。
- UI refresh 仍是混合式：controller observer events、panel-local manual refresh、tab switch
  refresh、command result 後局部 refresh 和 ChatPanel / agent Qt signal path 並存。第一個
  coordinator slice 已新增 `XBrainLab.ui.refresh_coordinator.refresh_after_command()`，real
  `Study` 的 `execute_application_command()` 會依 `CommandResult.changed_state` 刷新 dataset /
  preprocess / training / analysis panels、main info panel 和 assistant backend status；query-only
  evaluation / visualization refresh 會關閉二次 refresh，coordinator 也有 re-entrancy guard。這是
  target direction 的 first slice，不是 target closure。最新 Training sidebar refresh cleanup 已把
  generate dataset、configure model/settings、start training 和 clear history 的 post-command
  `check_ready_to_train()` 改成 legacy fallback-only；real `Study` success path 的 readiness refresh
  交給 coordinator。Dataset action handler 也已把 smart parse、batch metadata 和 remove files 的
  post-command `panel.update_panel()` 改成 legacy fallback-only；Data Interpretation import/apply
  和 recipe reload 的 service-success path 也不再直接呼叫 `panel.update_panel()`，由 command
  refresh coordinator 根據 `ApplyInterpretationCommand.changed_state` 刷新；post-load label
  compatibility 的 service-backed `ImportLabelsCommand` 成功 path 也改成 legacy fallback-only
  manual refresh；direct `LoadDataCommand` compatibility fallback 的 service-success path 也不再
  手動刷新；Dataset sidebar 的 channel selection 和 clear dataset service-success path 也已移交
  coordinator；Dataset table inline subject/session metadata edit 的 service-success path 也不再
  手動刷新；Preprocess sidebar 的 filter / resample / rereference / normalize / epoch / reset
  service-success path 也不再手動刷新 panel 或 main info；Visualization control sidebar montage /
  saliency service-success path 也不再直接呼叫 `on_update()`。最新 architecture guard 又把
  service-backed command 後的 direct local refresh 納入 `tests/architecture_compliance.py`：
  UI action 在 `execute_application_command()` 後不可再直接呼叫 `update_panel()`、
  `check_ready_to_train()`、`notify_update()`、`on_update()`、`update_info_panel()` 或
  `refresh_backend_status()`，除非是 explicit `refresh=False` query path 或 failure / legacy
  fallback branch。最新 guard hardening 又把 legacy missing-result branch 收緊：`result is None`
  branch 不可直接呼叫 local refresh method，應透過 explicit legacy-result helper；`result.failed`
  branch 仍可做 local restore / warning refresh。最新 tab-switch cleanup 又把
  `MainWindow.switch_page()` 的 panel-index refresh mapping 移到
  `refresh_after_navigation()`，讓 command result refresh 和 navigation refresh 都由
  `refresh_coordinator` 承接；navigation refresh 現在也會更新 aggregate info panel 和 assistant
  backend status，不再只刷新 selected panel。最新 navigation hardening 又讓
  `refresh_after_navigation()` 使用與 command / observer refresh 相同的 same-main-window
  re-entrancy guard，避免 tab switch refresh 被 nested refresh 重新觸發。最新 observer refresh cleanup 又把單純的
  `event -> update_panel()` bridge 收斂到 `BasePanel.refresh_from_observer()`，再委派
  `refresh_coordinator.refresh_after_observer()`；simple observer refresh 現在會刷新事件來源
  panel、aggregate info panel 和 assistant backend status。這保留 observer bridge 語意，但不再讓
  每個 panel 直接接 `update_panel()`。最新 Dataset import-finished callback cleanup 又把 legacy import success
  refresh 收斂到 `data_changed` simple refresh bridge；`import_finished` 現在只負責 warning
  message，不再二次手動刷新 Dataset panel。後續 duplicate observer cleanup 也移除了
  PreprocessPanel / TrainingPanel 對 dataset `import_finished` 的 simple refresh listener；legacy import
  success refresh 只由 dataset `data_changed` 擁有。InfoPanelService 也不再訂閱 dataset
  `import_finished`；latest follow-up 又讓 MainWindow product runtime 建立
  `InfoPanelService(observe_controller_events=False)`，所以 aggregate info refresh 由
  `refresh_coordinator` shared-status path 呼叫 `MainWindow.update_info_panel()` -> `notify_all()`，
  不再同時由 InfoPanelService 自己的 `data_changed` / `preprocess_changed` observer bridge
  二次更新。最新 InfoPanelService lookup cleanup 又把 direct
  `Study.get_controller(...)` bridge / list fallback 收進 `get_legacy_controller_from_study()`；
  real `Study` aggregate summary 只走 `QueryStateCommand(query="data_lists", include_objects=True)`
  或 command-coordinator `notify_all()`，mock / legacy context 才可建立 controller observer bridge。
  最新 UI command-helper boundary 又把 InfoPanelService 的 data-list query 改成
  `execute_application_command(..., refresh=False)`，並新增 architecture guard 阻擋 UI code 直接
  `BackendFacade(...).service.execute()`；`application_capabilities.py` 是唯一保留的 UI command
  execution helper。
  最新 architecture
  guard follow-up 也會阻止新的 `import_finished` simple refresh bridge：
  若需要處理 import warnings 或特殊 event 語意，必須用 named callback handler。最新 helper cleanup 又把 Dataset / Preprocess / Training / Evaluation /
  Visualization 的 simple observer bridge call sites 改成 `BasePanel._create_refresh_bridge()`，
  讓後續 panel 不必重複拼 `_create_bridge(..., refresh_from_observer)`。最新 architecture guard
  已把 `_create_bridge(..., self.update_panel)` 和 direct
  `_create_bridge(..., self.refresh_from_observer)` 納入 `tests/architecture_compliance.py`；
  simple refresh 必須走 `_create_refresh_bridge()`，callback-specific handler 仍可用 named handler。
  最新 observer-handler guard 也會檢查這些 named handler：若 `_create_bridge()` 綁定的是
  `data_changed`、`preprocess_changed`、training lifecycle / progress 或 visualization refresh
  event，handler 在做完 event-specific local side effect 後必須呼叫
  `refresh_after_observer()`，避免下一個 callback 又回到只刷新局部 panel 的舊模式。
  最新 downstream coordinator cleanup 又讓
  `training_changed` command result 刷新 Evaluation / Visualization readiness、`epoch_changed`
  刷新 Visualization readiness、`evaluation_changed` 也刷新 Visualization readiness，減少這些
  analysis panels 對 observer-only refresh 的依賴。最新 TrainingPanel callback cleanup 又讓
  `training_started`、`training_stopped`、`config_changed` 和 `history_cleared` 這些高層事件
  handler 在完成自身 UI 更新後刷新 aggregate info panel 和 assistant backend status；
  最新 follow-up 也把 high-frequency `training_updated` 納入 training-owner coordinator scope，
  live progress update 不再只停在 TrainingPanel 自身刷新。最新 observer
  event-scope cleanup 又讓 `data_changed` 和 `preprocess_changed` 這兩種 known observer event
  使用 coordinator changed-state scope：`data_changed` 只由 DatasetPanel owner bridge 一次刷新
  Dataset / Preprocess / Training，`preprocess_changed` 只由 PreprocessPanel owner bridge 一次刷新
  Preprocess / Training / Visualization；training lifecycle events 則由 TrainingPanel owner
  callback 一次刷新 Training / Evaluation / Visualization。最新 visualization observer cleanup
  也把 `montage_changed` / `saliency_changed` 納入 coordinator route，由 VisualizationPanel
  owner bridge 刷新 Visualization 和 shared status，避免 helper / secondary context 自己刷新錯誤 panel。
  最新 shared info refresh cleanup 也修正 `MainWindow.update_info_panel()`：coordinator 現在會透過
  `InfoPanelService.notify_all()` 更新已註冊的 aggregate info panels，而不是只嘗試不存在的
  `MainWindow.info_panel`。最新 Preprocess legacy/mock refresh cleanup 也把 epoch / reset 後仍保留的
  shared-status fallback 改成 `refresh_shared_status()`，所以 compatibility path 不再只刷新 aggregate
  info 而漏掉 assistant backend status。最新 Aggregate Info query-failure cleanup 又讓 real
  `Study` `InfoPanelService` 在 `QueryStateCommand(query="data_lists", include_objects=True)`
  失敗時回空 summary 並記 log，不再 fallback 到 dataset / preprocess controller list reads 顯示另一套
  stale truth。其他同事件 subscriber 不再重複刷新。2026-05-05 reviewer finding 已明確接受：
  這些進展仍只能稱為 command-driven refresh baseline / partial alignment，不阻塞目前
  validation/local eval closure，但在 product-complete 前仍必須完成 centralized coordinator
  closure。後續仍要把
  剩餘 manual refresh / callback-specific observer path 收斂或明確標成 event bridge。
- product runtime mutating workflow 不應 silent fallback 到 controller mutation。現有
  controller fallback 只可保留在 explicit mock / unit-test compatibility 或 isolated legacy
  adapter path；後續要繼續 audit dataset import、metadata / smart parse / remove、training
  split / model option / start-stop / clear-history 等 UI path，確認 real `Study` success path
  不依賴 controller mutation 成功。最新 Training sidebar fallback audit slice 已新增
  `run_legacy_controller_fallback()`：split cleanup / generate dataset、model selection、training
  settings、start / stop training 和 clear history 的 controller fallback 現在只允許 mock /
  legacy non-`Study` context；若 real `Study` command helper 意外回 `None`，會拒絕 fallback
  並顯示使用者可理解的安全訊息，而不是 silent controller mutation 或 raw developer wording。後續 Preprocess、Dataset、Visualization 和
  AgentManager fallback audit 已沿用同一 helper；最新 follow-up 也把 Visualization sidebar
  `Set Montage` 的 missing-result branch 從 silent no-op 改成同一 explicit mock / legacy fallback
  boundary。最新 Dataset import boundary slice 也讓 `scan_source` capability 存在時的 file import
  不再把 Data Interpretation command-sequence unavailable 旁路成 `LoadDataCommand` / legacy
  `import_files`；只有 mock / legacy context 才能走舊 fallback。最新 Training model-selection
  cleanup 又移除了一個 service-success path 對 stale controller state 的依賴：
  `ConfigureTrainingCommand` 成功後，UI 以 command success 和剛選定的 model holder 呈現
  success，不再回讀 `TrainingController.get_model_holder()` 來否定 command result。legacy fallback
  branch 仍保留 controller verification。最新 architecture guard 已把這條規則納入
  `tests/architecture_compliance.py`：service-backed success path 不可在
  `execute_application_command()` 後用 `TrainingController.get_model_holder()` 這種 controller
  echo 重新判定 command success；echo reads 只允許在 explicit legacy fallback branch。
  最新 Training split cleanup 又把 existing-dataset replacement 判斷改成 backend capability
  truth：real `Study` path 若 `generate_dataset` 只因 existing dataset / trainer 被 block，但
  `clear_datasets` enabled，UI 會要求 confirmation 並先送 `ClearDatasetsCommand`，不再依賴
  stale `TrainingController.has_datasets()` / `get_trainer()` 判斷是否要清資料。
  最新 Training split dialog context cleanup 新增
  `QueryStateCommand(query="dataset_generation_context", include_objects=True)`；real `Study`
  Training sidebar 會把 service-backed epoch/generator context 傳入 `DataSplittingDialog`。最新
  dialog-level follow-up 也讓 real `Study` context 在缺少 explicit context 時回 `None`，不再自行讀
  stale `TrainingController.get_epoch_data()` / `get_dataset_generator()`；controller reads 只留在
  mock / legacy dialog fallback。
  最新 Data Splitting preview thread cleanup 讓 preview restart / dialog close 會 interrupt
  active `DatasetGenerator` 並 short-join preview worker；這是 focused lifecycle smoke，不是
  long-running dataset-generation soak test。
  最新 Start Training cleanup 也把 start gate 改成 backend `train` capability 優先：real
  command-capable path 若 capability enabled，stale `TrainingController.is_training()` 不會再讓
  Start button silently skip `TrainCommand`；controller running check 只留給 no-capability mock /
  legacy path。最新 architecture guard follow-up 又把這類 pre-command readiness bug 納入
  `tests/architecture_compliance.py`：有 `get_command_capability()` 的 UI command path 不可用
  `controller.is_training()`、`has_datasets()` 或 `get_trainer()` 做 gating，除非明確在
  `capability is None` legacy branch。最新 guard extension 也把
  `validate_ready()`、`has_model()`、`has_training_option()` 納入 Training readiness echo
  防線；`check_ready_to_train()` 現在用明確 no-capability branch 讀 legacy controller
  readiness，不再把 controller readiness call 藏在 capability conditional expression 裡。最新
  follow-up 又把這些 no-capability Training preflight reads 包進
  `run_legacy_controller_fallback()`：real `Study` 如果 capability helper / command helper
  unexpectedly unavailable，Start button 會 disabled 並顯示 state unavailable，Data Splitting /
  Model/Settings configuration、Stop Training 和 Clear History 會顯示 user-facing blocked warning，
  不再回讀 stale `TrainingController`。
  最新 Training settings cleanup 又把設定 dialog 預設值改成先讀
  `QueryStateCommand(query="state")` 的 `state.training.training_option` snapshot；dialog
  `controller.get_training_option()` 只保留給 query unavailable 的 mock / legacy path。
  最新 dialog-level hardening 又讓 `TrainingSettingDialog.load_settings()` 本身受
  `run_legacy_controller_fallback()` 約束；real `Study` 若沒有 service-backed `initial_option`，
  會保留安全預設，不回讀 stale controller defaults。
  最新 Training history cleanup 新增 `QueryStateCommand(query="training_history",
  include_objects=True)`；real `Study` `TrainingPanel.update_loop()` 會用 service-backed
  history rows 更新 table / plot selection，不再從 injected `TrainingController.get_formatted_history()`
  讀 stale history。controller formatted-history read 只保留在 query unavailable 的 mock /
  legacy path。最新 query-none fallback boundary 也讓 real `Study` training-history query 意外
  回 `None` 時清成 empty training display，不再回讀 stale controller history。
  最新 Stop Training fallback warning slice 也讓 real `Study` stop command 意外無法 dispatch 時
  顯示 `Stop Training Blocked`，不再把 legacy fallback refusal 外拋成 raw RuntimeError。
  最新 Clear History fallback warning slice 同樣讓 real `Study` clear-history command 無法 dispatch
  時顯示 `Clear History Blocked`，不再用 generic error 包住 fallback refusal。
  最新 Preprocess Reset fallback warning slice 也讓 real `Study` reset-preprocess command 無法
  dispatch 時顯示 `Reset Blocked`，不再把 safe fallback refusal 包成 generic critical error。
  最新 Dataset Clear fallback warning slice 也讓 real `Study` reset-session command 無法 dispatch
  時顯示 `Clear Dataset Blocked`，不再把 fallback refusal 包成 generic critical error。
  最新 Channel Selection apply fallback warning slice 也讓 real `Study` channel-selection apply
  command 無法 dispatch 時顯示 `Channel Selection Blocked`，不再包成 generic critical error。
  最新 Generate Dataset apply fallback warning slice 也讓 real `Study` dataset-generation command
  無法 dispatch 時顯示 `Data Splitting Blocked`，不再外拋 legacy fallback exception。
  最新 Data Splitting clear fallback warning slice 也讓 real `Study` clear-datasets preflight command
  無法 dispatch 時顯示 `Data Splitting Blocked`，不再外拋 legacy fallback exception。
  最新 Model Selection fallback warning slice 也讓 real `Study` configure-training model command
  無法 dispatch 時顯示 `Model Selection Blocked`，不再外拋 legacy fallback exception。
  最新 Training Settings fallback warning slice 也讓 real `Study` configure-training option command
  無法 dispatch 時顯示 `Training Settings Blocked`，不再外拋 legacy fallback exception。
  最新 Start Training fallback warning slice 也讓 real `Study` train command 無法 dispatch 時顯示
  `Start Training Blocked`，不再把 safe fallback refusal 包成 generic critical error。
  最新 Data Splitting context query-none slice 也讓 real `Study` dataset-generation context query
  無法 dispatch 時顯示 `Data Splitting Blocked`，不再開啟缺少 service context 的 splitting dialog。
  最新 Remove Files fallback warning slice 也讓 real `Study` remove-files command 無法 dispatch
  時顯示 `Remove Files Blocked`，不再外拋 legacy fallback exception。
  最新 Metadata Update fallback warning slice 也讓 real `Study` inline / context-menu metadata
  update command 無法 dispatch 時顯示 `Metadata Update Blocked`，不再外拋 legacy fallback
  exception。
  最新 Smart Parse apply fallback warning slice 也讓 real `Study` smart-parse apply command
  無法 dispatch 時顯示 `Smart Parse Blocked`，不再外拋 legacy fallback exception。
  最新 Label Import fallback warning slice 也讓 real `Study` label-import apply command
  無法 dispatch 時顯示 `Label Import Blocked`，不再把 legacy fallback refusal 包成 generic
  `Failed: ...` error。
  最新 Smart Parse filename fallback warning slice 也讓 real `Study` state query 無法提供
  filenames 時顯示 `Smart Parse Blocked`，不再回讀 stale controller filename list。
  最新 Direct Load compatibility fallback warning slice 也讓 real `Study` direct `LoadDataCommand`
  compatibility command 無法 dispatch 時顯示 `Interpretation Blocked`，不再嘗試 controller
  `import_files()` 或包成 generic import error。
  最新 Preprocess operation fallback warning slice 也讓 filtering / resampling / re-reference /
  normalization / epoching 的 real `Study` command-`None` path 顯示對應 Blocked warning，不再
  包成 generic `failed: ...` error 或嘗試 controller mutation。
  最新 Dataset inline metadata fallback warning slice 也讓 table 直接編輯 subject/session 時，
  real `Study` `UpdateMetadataCommand` 無法 dispatch 會顯示 `Metadata blocked` 並刷新表格，
  不再外拋 legacy fallback exception。
  最新 AgentManager montage fallback warning slice 也讓 assistant montage confirmation 在
  real `Study` `ApplyMontageCommand` 無法 dispatch 時顯示 `Montage setup blocked`，不再把
  legacy fallback refusal 外拋成 raw RuntimeError 或嘗試 preprocess controller mutation。
  最新 DatasetPanel query-none render fallback boundary 也讓 real `Study` table refresh 在
  `QueryStateCommand(query="data_lists")` 意外無法 dispatch 時清成空表並記 log，不再回讀
  stale `DatasetController.get_loaded_data_list()`。
  最新 architecture guard follow-up 又把這類 stale render fallback pattern 納入
  `tests/architecture_compliance.py`：`result is None` branch 若要回讀 controller render state
  必須走 `run_legacy_controller_fallback()`，不能裸讀 stale controller data。
  最新 Dataset sidebar render cleanup 又把 `is_locked()` / `has_data()` 納入 guard：real
  `Study` button state 和 tooltip 有 backend capability 時不再先讀 stale controller lock/data
  state；controller lock/data reads 只保留在 explicit no-capability legacy branch。最新
  no-capability follow-up 又把這些 legacy render / Channel Selection preflight reads 包進
  `run_legacy_controller_fallback()`；real `Study` 若 capability lookup unexpectedly unavailable，
  source / recipe / channel / smart-parse / label buttons 會 disabled 或顯示 unavailable/blocked
  文案，不再回讀 stale `DatasetController.is_locked()` / `has_data()`。
  最新 Dataset action handler follow-up 也把 file import、folder/BIDS source flow 和 Smart Parse
  的 no-capability `is_locked()` / `has_data()` preflight reads 包進 explicit legacy helper；real
  `Study` 不再用 stale `DatasetController` state 擋住 Data Interpretation / Smart Parse action
  gating，direct-load compatibility 仍只走 service command，不能 fallback controller mutation。
  最新 Preprocess sidebar render cleanup 也把 `update_sidebar()` 的 epoched/lock render state
  收回 backend capability surface：real `Study` 有 `preprocess` / `create_epoch` capability 時不再讀
  stale `PreprocessController.get_preprocessed_data_list()`；該 controller read 只保留給
  no-capability mock / legacy path，並已納入 architecture compliance guard。最新
  no-capability follow-up 又把 `check_lock()` / `check_data_loaded()` 的 epoched/data fallback
  reads 包進 `run_legacy_controller_fallback()`；real `Study` 若 `preprocess` capability lookup
  unexpectedly unavailable，會顯示 user-facing blocked/unavailable warning，不再回讀 stale
  `PreprocessController.is_epoched()` / `has_data()`。最新 architecture guard follow-up 又收緊
  `tests/architecture_compliance.py`：`capability is None` branch 也不可直接呼叫 controller
  readiness methods，必須走 explicit legacy helper；同時 `PreprocessSidebar.update_sidebar()` 的
  no-capability render list read 也收進 legacy render helper。
  最新 Dataset smart-parse cleanup 又把 parser dialog 的 file list 改成先讀
  `QueryStateCommand(query="state")` 裡的 `state.raw.files`；`DatasetController.get_filenames()`
  只保留在 query unavailable 的 mock / legacy fallback helper。
  最新 Preprocess epoching cleanup 修掉另一個 capability 混用：`open_epoching()` 現在以
  `create_epoch` capability 判定是否可進入 epoch dialog；當 `create_epoch` enabled 時，不會再被
  `preprocess` capability 的 blocked reason 透過 `check_lock()` / `check_data_loaded()` 誤擋。
  舊 controller lock/data checks 只保留給 no-capability mock / legacy path。最新 guard follow-up
  又讓 epoch dialog 的 preprocessed object list 先走 `QueryStateCommand(query="data_lists",
  include_objects=True)`，`PreprocessController.get_preprocessed_data_list()` 只保留在
  no-capability mock / legacy path。最新 query-unavailable fallback boundary 也讓 real `Study`
  若 query helper 意外回 `None`，會 block epoch dialog source selection，而不是讀 stale
  controller list。最新 re-reference dialog cleanup 也改用同一個
  `QueryStateCommand(query="data_lists", include_objects=True)` 取得 dialog data source；real
  command-capable path 不再用 stale `PreprocessController.get_preprocessed_data_list()` 開
  `RereferenceDialog`。
  最新 Evaluation panel cleanup 則把 readonly `EvaluateCommand` 結果接到顯示 gate：real
  `Study` path 若 ApplicationService 回 blocked / unavailable evaluation，panel 不再繼續讀
  stale injected `EvaluationController.get_plans()` 來顯示過期 plan，而是清成
  `No Data Available`。後續 object-payload cleanup 又讓 successful
  `EvaluateCommand(include_objects=True)` 回傳 UI render 所需的 plan objects、pooled metrics 和
  model summaries；real `Study` panel 有 service payload 時不再讀 stale injected
  `EvaluationController.get_plans()` / `get_pooled_eval_result()` /
  `get_model_summary_str()`。最新 query-none fallback boundary 也讓 real `Study`
  `EvaluateCommand` 意外回 `None` 時清成 no-data，不再回讀 stale
  `EvaluationController.get_plans()`。最新 stale-selection fallback boundary 又讓 query-none 狀態下
  留存的 average/summary selection 不會回讀 stale
  `EvaluationController.get_pooled_eval_result()` / `get_model_summary_str()`。
  這個 object payload flag 是 UI-only：automation / MCP `evaluate`
  schema 不暴露也不接受它，避免 external client 要求非序列化 UI object。
  最新 Visualization panel cleanup 也把 readonly `VisualizeCommand` 結果接到 controls/render
  gate：visualization blocked / unavailable 時不再讀 stale injected
  `VisualizationController.get_trainers()`，而是保持 `Select a plan` 並用使用者可讀訊息提示
  目前沒有 visualization views ready。後續 object-payload cleanup 又讓 successful
  `VisualizeCommand(include_objects=True)` 回傳 UI render 所需的 trainer objects 和 averaged
  records；real `Study` panel 有 service payload 時不再讀 stale injected
  `VisualizationController.get_trainers()` / `get_averaged_record()`。這個 object payload flag
  也是 UI-only：automation / MCP `visualize` schema 不暴露也不接受它。Visualization sidebar 的
  `Export Saliency` 也補上 readonly
  `SaliencyCommand` export gate；saliency output 不可用時不再讀 stale trainer list 開 export dialog。
  最新 export trainer cleanup 又讓 saliency 可匯出時改用
  `VisualizeCommand(include_objects=True)` 的 service-backed `trainer_objects` 開 export dialog；
  `panel.get_trainers()` / `VisualizationController.get_trainers()` 只留在 query unavailable 的
  mock / legacy fallback helper。最新 follow-up 又讓 `VisualizationPanel.get_trainers()` 在已有
  failed ApplicationService visualization query 時直接回空 list，不再 fall back 到 stale
  controller trainers。最新 query-none render fallback boundary 也讓 real `Study`
  `VisualizeCommand(include_objects=True)` 意外回 `None` 時保持 empty controls，而不是回讀 stale
  `VisualizationController.get_trainers()`。最新 average stale-selection fallback boundary 又讓
  query-none 狀態下留存的 Average selection 不再回讀 stale
  `VisualizationController.get_averaged_record()`。
  最新 saliency settings cleanup 也把設定 dialog 的預設值改成先讀 readonly `SaliencyCommand`
  summary diagnostics；`VisualizationController.get_saliency_params()` 只保留在 query unavailable
  的 mock / legacy fallback helper，避免 real `Study` UI 用 stale controller params 填 dialog。
  最新 montage setup cleanup 也把 channel-name dialog defaults 改成先讀
  `QueryStateCommand(query="state")` 裡的 `state.epoch.channel_names`；Visualization sidebar
  和 AgentManager montage picker 都用這個 shared state query 取 channel names，不再由產品
  UI 直接讀 `study.epoch_data` / controller channel list 來決定 dialog choices。controller
  `get_channel_names()` 和 direct Study epoch reads 只保留在 query unavailable 的 mock / legacy
  fallback helper。最新
  Visualization fallback language slice 又讓 Montage / Saliency Settings / Export Saliency 的
  real `Study` query-none 或 apply-none fallback refusal 顯示 shared product warning，不再把
  `LegacyControllerFallbackUnavailableError` 外拋到 UI slot。
  最新 Preprocess panel render cleanup 也讓 history / preview / plotter refresh 先走
  `QueryStateCommand(query="data_lists", include_objects=True)`；real `Study` refresh 不再從
  `PreprocessPanel.update_panel()` 直接讀 stale `PreprocessController.get_preprocessed_data_list()`。
  最新 follow-up 把同一 query helper 下沉給 `PreprocessPlotter.plot_sample_data()`：若 caller
  沒有顯式傳入 data list，plotter 會先查 ApplicationService data-list truth；若 caller 只顯式
  傳入 current data 但沒有傳 original overlay，plotter 也會用同一 query 取得 original list，而不是
  直接讀 `controller.study.loaded_data_list`。只有 query unavailable 的 mock / legacy path 才讀
  controller list。最新 render fallback boundary 也讓
  real `Study` 的 panel refresh / direct plotter call 若意外拿到 query `None`，會降級為 no-data
  render，而不是回讀 stale `PreprocessController` list。
  最新 Preprocess plotter cleanup 又替 async PSD worker result 加上 generation guard；快速重繪時
  舊 PSD worker 結果不會回寫到新的 frequency plot。這是 UI responsiveness / stale result guard，
  不是 long-running preprocessing performance soak。
  最新 Dataset table render cleanup 也讓 `DatasetPanel.update_panel()` 先走同一個 `data_lists`
  query；real `Study` table rows 不再從 `DatasetController.get_loaded_data_list()` 取得，該 read
  只留給 no-ApplicationService mock / legacy rendering。
  `tests/architecture_compliance.py` 也會阻擋
  UI `result is None` branch 直接 controller mutation。最新 guard follow-up 又會阻擋 UI
  product path 直接呼叫 `controller.update_metadata()` / `controller.start_training()` 這類
  mutating controller method；最新 direct Study state guard 也會阻擋產品 UI 直接讀
  `study.loaded_data_list`、`study.epoch_data`、`study.trainer` 這類 mutable state；合法 controller mutation 必須在 `run_legacy_controller_fallback()`
  或明確 legacy / fallback helper 裡。最新 named-controller receiver guard 又把
  `self.preprocess_controller` 這類具名 controller attribute 納入同一條規則，避免 direct
  mutation 因為不是剛好叫 `self.controller` 而逃過 static audit。後續 runtime alignment slice 也讓
  `find_study()` 能從 `self.<name>_controller.study` 找到 real `Study`，因此具名 controller
  context 會走 ApplicationService capability / fallback refusal，而不是被誤判為 legacy context。
  最新 observer wiring fallback guard 又把 Evaluation / Visualization panel 的
  `controller.study.get_controller("training")` 退路收進 explicit legacy helper；real `Study`
  panel 若缺 MainWindow 注入的 `TrainingController`，不再自己回頭找 controller tree 來建立
  observer bridge。
  最新 panel constructor / AgentManager lookup guard 也把五個 workflow panel 的
  `parent.study.get_controller(...)` fallback 和 AgentManager 初始化時的
  `study.get_controller("preprocess")` 收進 mock / legacy-only helper；product runtime 的 controller
  wiring 現在應由 MainWindow injection 負責，static architecture compliance 也會擋住新的 direct
  Study controller lookup。
  最新 InfoPanelService lookup cleanup 也移除了 direct `Study.get_controller(...)` 例外：
  real `Study` 的 aggregate info bridge / list fallback 不再回讀 dataset / preprocess controller，
  mock / legacy compatibility 才能經 explicit helper 使用 controller bridge。
  最新 no-refresh command guard 也讓 UI 中的 `execute_application_command(..., refresh=False)`
  只可用於 read/query commands；mutating command 必須保留 command-driven refresh。最新
  legacy-mutation helper guard 也要求會直接 mutate controller 的 legacy / fallback helper 只能在
  `run_legacy_controller_fallback()` gate 內被呼叫，避免 helper 名稱本身變成繞過 product runtime
  policy 的旁路。這是 product runtime fallback boundary，不是 controller 已完全退場；下一個
  architecture cleanup milestone 仍是確認 product runtime mutating path 不 silent fallback 到
  controller mutation，controller fallback 只可保留給 explicit mock / unit-test compatibility 或
  isolated legacy adapter。
- Agent mapped tools 的一批 path 已直接回 `CommandResult`；`load_data` 也已先做 directory
  expansion 再進 command surface，但不再出現在 Empty / Data Loaded / Preprocessed stage 的
  primary prompt；`attach_labels` 也已從這些 stage 的主工具語言移除。read-only
  `list_files` / `get_dataset_info` 會被正規化成 typed result。visible transcript 只顯示使用者語言；raw tool payload 保留在 diagnostics。
  最新 agent execution boundary cleanup 又讓 real `Study` 下的 mapped workflow tool 若無法組成
  ApplicationService command（例如缺 bandpass low/high frequency），會回 structured input failure
  並要求補資訊，不會退回 legacy real-tool execution。
  `set_montage` 和 `switch_panel` 仍是 UI request path；真正 montage apply 在 confirmation
  後走 `ApplyMontageCommand`。AgentManager 和 Visualization sidebar 現在共用 montage position
  normalizer，confirmed positions 會先轉成 JSON-safe float tuples，malformed coordinate vectors
  不會進入 ApplicationService。
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
  formal deterministic / primary / fallback artifact 都已刷新為 `121 / 121`，包含 recipe reload
  `eeg_file_remap` / `label_carrier_remap` 和 missing remap target clarification。後續 fast
  changed-case gate 已把 source suite 增到 `122` cases，新增中文「幫我貼標籤」missing-input
  clarification case，並通過 `1 / 1` deterministic changed-case artifact；這不是正式 local
  primary / fallback rerun，也不能更新 thesis score claim。
  scorer 已收緊 substitute-tool handling：direct blocked command 可以由 verifier/capability
  policy 擋下，但替代工具不再被誤算成 pass。這解除先前 `54` case 數不足、
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
  artifact 也已完成；local HTTP MCP transport baseline 已完成並有
  `artifacts/mcp/http-walkthrough.*`，同 artifact 現在覆蓋 HTTP train job status / cancel。
  Evaluation / visualization jobs、job persistence / recovery 和 full client certification 尚未完成。
- Data Interpretation 目前是強化中的 baseline wizard，不是 final import system。仍缺 mature
  embedded label editor、raw trigger selector、complex GDF / MAT anchor reconciliation、XDF /
  LSL full parser、full real-data manual certification 和更成熟的 recipe diff / review UX。這是
  product follow-up，不應被現有 UI replay / backend JSON / eval dashboard 包裝成 final import
  system。

## 目前執行中

1. 繼續 backend architecture cleanup：`ApplicationService` 已拆出 Data Interpretation、
   Analysis、Training、Dataset Generation、Lifecycle、Data Compatibility 和 Data Table command
   services、Preprocess command service，以及 State / Query services；下一輪應檢查是否還有
   UI / agent / MCP 旁路或 wrapper compatibility 心智模型，而不是再把 workflow 塞回 service。
   `UI Command Refresh Coordinator + Controller Fallback Audit` 已完成第一個集中 refresh
   helper slice；接下來要把剩餘 panel-local manual refresh / controller observer path 和
   product runtime fallback 全面盤點，明確分離 mock / legacy compatibility fallback。
   Training sidebar 已完成第一個 explicit fallback boundary slice；Preprocess sidebar 也已把
   filter / resample / rereference / normalize / epoch / reset fallback 改成 mock / legacy
   non-`Study` only。Dataset data-table/action fallback 也已收斂 metadata edit / batch metadata、
   smart parse、remove files、direct file import、clear dataset、channel selection 和 post-load label
   compatibility fallback。Visualization saliency settings 和 AgentManager montage confirmation
   fallback 也已收斂到同一 helper；Visualization sidebar `Set Montage` missing-result fallback
   也已收斂到同一 helper；Dataset file import 在 real command surface 存在時不再從 failed
   Data Interpretation command sequence 退到 direct load compatibility。現在剩餘 `result is None` path 主要是 service-unavailable
   blocked / critical / false returns 或已顯式標記的 mock / legacy compatibility fallback，不再是
   silent product controller mutation。`tests/architecture_compliance.py` 現在也會檢查 UI 的
   `result is None` branch 不可直接呼叫 controller mutation；mock / legacy-only fallback 必須經過
   `run_legacy_controller_fallback()`。最新 observer-handler guard 也把 callback-specific
   observer path 納入 architecture compliance：known refresh events 的 named handler 必須呼叫
   `refresh_after_observer()`，不能只做局部 `update_loop()` / local UI 更新。最新 named-controller
   receiver guard 也讓 `self.preprocess_controller` / `preprocess_controller` 這類 controller
   receiver 受到 direct mutation static audit 約束；`find_study()` 也已同步支援具名 controller
   context，避免 runtime helper 和 static guard 對 controller receiver 的判斷不一致。最新
   no-refresh command guard 也把 `refresh=False` 限制在 `QueryStateCommand` / `EvaluateCommand`
   / `VisualizeCommand` / query-only `SaliencyCommand()`，避免 mutating command 成功後跳過
   coordinator refresh。最新 legacy-mutation helper guard 又要求直接 mutate controller 的
   legacy/fallback helper 呼叫必須位在 `run_legacy_controller_fallback()` 內，避免 isolated
   helper 被誤用成產品 runtime fallback。
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
   ChatPanel reset stale UI。最新 Dataset sidebar polish 也把 `Channel Selection` 從 success-green
   action 改成中性 workflow action；這個按鈕會修改資料，不應用成功狀態顏色誤導使用者。仍要補
   mature import wizard editing、assistant main-window narrow composition 和整體產品感。
6. 將 `121` case remap-expanded tool-call dashboard 整理成 thesis report evidence；目前
   formal deterministic / primary / fallback 都是 `121 / 121`，但不要把它擴張成 UI /
   launcher / import wizard 產品完成 claim。最新 source suite 已因 `zh-label-action-missing-input`
   增至 `122` cases，這一片只跑 `1 / 1` deterministic changed-case fast gate；正式 `122`
   case claim 要等 release / thesis gate 重跑。日常 tool-call 修正不可預設 full primary / fallback x3；
   validation gate 分成 deterministic changed-case fast gate、primary subset candidate gate，以及
   release / thesis full local gate。full fallback x3 需要先做 VRAM / disk / cache preflight，並把
   latency / resource pressure 寫進 artifact；deterministic CLI 現在也要求預設 fast gate 必須指定
   `--case-id` / `--case-family` / `--case-limit` subset，full-suite deterministic dashboard refresh
   必須顯式帶 `--eval-gate release` 或 `--eval-gate thesis`；local eval CLI 現在要求 full-suite repeat `3`
   local run 顯式帶 `--eval-gate release` 或 `--eval-gate thesis`，且會在 VRAM high pressure 時
   先產生 `resource_preflight.*` 並停止，平常請用 deterministic / changed cases / primary
   subset gate。
7. external EEG dataset experiment / statistical reporting 只作 pipeline support，不作 thesis
   主評分。

## 相關文件

- [target/README.md](target/README.md)
- [planning/now.md](planning/now.md)
- [operations.md](operations.md)
- [validation/README.md](validation/README.md)
