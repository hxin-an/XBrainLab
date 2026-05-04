# XBrainLab Implementation Log

最後更新：`2026-05-05`

## 這份文件的用途

這份文件只記錄「高層次產品狀態」和「重要工程決策」。

它不再承擔逐 slice 實作細節、TDD 紅燈、完整 command output 或 artifact 清單。那些內容放在
`docs/records/worklog.md`。如果 implementation log 和 worklog 寫到同一件事，這裡只保留：

- 哪條產品主線前進了
- 目前可支撐什麼 claim
- 主要 evidence 入口在哪裡
- 還不能宣稱完成的是什麼
- 下一手 owner 應該看哪裡

## 文件分工

| 文件 | 職責 |
| --- | --- |
| `docs/current.md` | 目前真相：現在能做什麼、不能宣稱什麼、主要 blocker。 |
| `docs/planning/roadmap.md` | 產品主線：哪些 track 已有 baseline、哪些仍未達成成品。 |
| `docs/planning/now.md` | 短期施工焦點：下一輪應優先處理什麼。 |
| `docs/validation/README.md` | 驗證邊界：哪些 evidence 支撐哪些 claim。 |
| `docs/records/implementation_log.md` | 高層狀態快照：產品主線進度與交接判斷。 |
| `docs/records/worklog.md` | 細節流水帳：實作切片、失敗嘗試、測試命令、artifact 細節。 |

## Entry 格式

```md
## YYYY-MM-DD 主題

### 狀態

### 已可宣稱

### Evidence 入口

### 不能宣稱完成

### 下一手重點
```

## 2026-05-05 Agent Data-Entry Tool Surface Downgrade

### 狀態

Agent stage prompt / tool exposure 已把 legacy `load_data / attach_labels` 從 Empty、
Data Loaded 和 Preprocessed 的 primary workflow language 移除。Context Assembler 現在會將
ApplicationService capability policy 與 stage allowlist 取交集，避免 backend compatibility
policy 把已降權的 legacy tools 重新放回 prompt。legacy tools 仍保留在 schema taxonomy、
parser / verification 和 compatibility service 裡，定位為相容入口而不是新資料入口主線。

### 已可宣稱

- In-app agent 的 primary data-entry prompt 已以 Data Interpretation scan / preview /
  validate / apply / recipe 為主。
- Backend capability policy 不能再單獨把 stage-filtered legacy data-entry tool 重新曝光到主
  prompt。
- Compatibility tools 仍可被 parser / verifier 辨識，沒有為了降權而刪掉相容面。

### Evidence 入口

- Source：`XBrainLab/llm/pipeline_state.py`
- Source：`XBrainLab/llm/agent/assembler.py`
- Source：`XBrainLab/llm/agent/confidence.py`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 legacy data-entry removal；UI post-load label compatibility、MCP/client-facing
  language 和長時間 ChatPanel workflow 仍要繼續盤點。
- 這不是 UI import wizard maturity、Windows human acceptance 或 product-complete claim。

### 下一手重點

下一輪應檢查 UI / MCP / docs 是否還把 `load_data / attach_labels` 當 primary workflow
language，並繼續把使用者入口收斂到 Data Interpretation wizard / recipe flow。

## 2026-05-05 Automation / MCP Legacy Compatibility Metadata

### 狀態

Headless command schema 和 MCP `tools/list` 現在會把 legacy data-entry commands 標成
compatibility，而不是 primary workflow。`load_data`、`attach_labels`、`import_labels` 的
`AutomationCommandSpec` 和 MCP `x_xbrainlab` metadata 都包含 `legacy_compatibility=True`、
`primary_workflow=False` 和 Data Interpretation preferred commands。

### 已可宣稱

- MCP/headless client-facing schema 不再把 legacy data-entry commands 包成新資料入口主線。
- Tool calls 仍走同一個 automation -> `ApplicationService.execute()` path，沒有新增 MCP backend
  truth。
- Compatibility commands 仍可被呼叫，但 schema 明確指向 Data Interpretation scan / preview /
  validate / apply / recipe flow。

### Evidence 入口

- Source：`XBrainLab/backend/application/automation.py`
- Source：`tests/unit/backend/application/test_automation.py`
- MCP integration evidence：`tests/integration/mcp/`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是 HTTP MCP、long-running job model 或 full MCP client certification。
- UI post-load label compatibility 仍需 mature import wizard replacement，不是靠 metadata 完成。

### 下一手重點

後續 MCP work 應處理 HTTP / long-running command job boundary、progress/cancel/recovery，以及
UI language 是否仍引導使用者走 post-load compatibility label path。

## 2026-05-05 Training Start Long-Running Confirmation

### 狀態

Training sidebar 的 `Start Training` button 現在會尊重 backend `train` capability 的
long-running confirmation boundary。當 capability 要求 confirmation 時，UI 會先用使用者語言提示
training 可能耗時並使用 CPU/GPU；使用者拒絕時不執行 command，service 成功時不 fallback 到
controller。

### 已可宣稱

- UI button path 和 ChatPanel agent path 都會對 `train` long-running action 做 human confirmation。
- Real `Study` path 仍透過 `TrainCommand` / `ApplicationService.execute()`，mock compatibility
  fallback 只保留給 unit-test / legacy adapter 情境。
- 已留下 automated Qt replay screenshot / visible text / button state artifact。

### Evidence 入口

- Source：`XBrainLab/ui/panels/training/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py`
- Artifact：`artifacts/ui/training-start-confirmation/`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是真人 Windows desktop training acceptance，也不是完整 training / evaluation / saliency UI
  長鏈驗收。
- 這不處理 MCP long-running job model；MCP training progress/cancel/recovery 仍是後續工作。

### 下一手重點

後續應把 button-driven train -> evaluate -> visualization / saliency flow 納入 UI-observable
walkthrough，並繼續補 Windows desktop human acceptance。

## 2026-05-05 Backend Command Boundary Cleanup

### 狀態

Backend command spine 持續從 `ApplicationService` god object 收斂成 focused command services。
Data Interpretation、analysis / visualization、training config / train-stop lifecycle、dataset
generation / split audit、reset lifecycle、legacy data / label compatibility 現在都有各自 service
boundary；metadata update / smart parse / remove file 也已移到 focused data-table boundary；
preprocessing operations 和 `create_epoch` 也已移到 focused preprocess boundary；state snapshot
assembly 和 `query_state` diagnostics 也已移到 focused state/query boundary。
`ApplicationService` 回到 dispatch、capability / confirmation gate 和 state/result envelope。
同一輪 UI runtime bypass audit 已修 Dataset direct file import 與 Preprocess reset 的
service-success controller fallback，讓 successful `CommandResult` 不會再被 UI 以 controller
mutation 重做一次。
後續 Training sidebar cleanup 也把重新 split 前的 dataset cleanup 和 Clear History 收回 typed
command path；Clear History 現在有使用者確認，successful service result 不再落回 controller
mutation。
Data Interpretation format capability taxonomy 也已抽成 focused module，讓 lifecycle module 不再
同時承接 scanner / candidate / format matrix 細節。
Metadata resolution / BIDS summary / recipe metadata rehydration 也已抽成 focused module，讓
Data Interpretation lifecycle module 的下一步拆分邊界更清楚。
Recipe serialization / JSON load-write / applied-interpretation-to-recipe builder 也已抽成
focused module，Data Interpretation lifecycle module 只保留 compatibility re-export。
Label carrier planner 也已抽成 focused module，Data Interpretation lifecycle module 不再直接承接
CSV / MAT parser helpers 或 label-anchor default selection。
Preview payload builder 和 safe / needs-confirmation / blocked validator 也已抽成 focused
review module，Data Interpretation lifecycle module 不再直接承接 review payload construction。
Source scanner / source classification 也已抽成 focused scan module，Data Interpretation
lifecycle module 不再直接承接 scan IO / source discovery。
Candidate builder / metadata override / event-class choice mapping 也已抽成 focused candidate
module，原大型 lifecycle module 現在主要保留 shared decision enum、applied lifecycle dataclass
和 compatibility re-exports。

### 已可宣稱

- Data Interpretation command lifecycle 由 `DataInterpretationCommandService` /
  `DataInterpretationApplyService` 承接。
- Evaluation / visualization / saliency / montage apply 由 `AnalysisCommandService` 承接。
- Model configuration、training option、train / stop、history cleanup 和 reset-time training config
  clear 由 `TrainingCommandService` 承接。
- Dataset generation、split config、split audit、rollback、split summary 和 dataset cleanup 由
  `DatasetGenerationCommandService` 承接。
- Reset preprocess、reset session、new session、downstream rollback 和 reset-time
  dependent-state clear 由 `LifecycleCommandService` 承接。
- 舊 `load_data`、`attach_labels`、`import_labels` 和 label helper 由
  `DataCompatibilityCommandService` 承接，並明確定位為 compatibility boundary。
- Metadata update、smart parse 和 remove files 由 `DataTableCommandService` 承接。
- Preprocessing operations 和 create epoch 由 `PreprocessCommandService` 承接。
- State snapshot assembly 和 query state diagnostics 由 `StateSnapshotService` /
  `QueryStateCommandService` 承接。
- Dataset direct file import 和 Preprocess reset 的 successful service path 不再 fallback 到
  controller mutation；controller fallback 僅保留給 mock / legacy `None` adapter 情境。
- Training sidebar 的 re-split dataset cleanup 和 Clear History destructive action 走
  `ClearDatasetsCommand` / `ClearTrainingHistoryCommand`，且 Clear History 有 confirmation。
- GDF / EDF-BDF / EEGLAB / BrainVision / FIF / MAT / CSV-TSV / TXT / BIDS events /
  XDF-LSL format capability boundary 由 `data_interpretation_formats.py` 承接。
- Subject / session / task / run metadata resolution、BIDS entity summary 和 recipe metadata
  rehydration 由 `data_interpretation_metadata.py` 承接。
- `ImportRecipe` serialization、recipe JSON load / write 和 applied interpretation recipe builder
  由 `data_interpretation_recipe.py` 承接。
- MAT / CSV / TSV / BIDS events / TXT label carrier planning、choice normalization、anchor /
  time model / granularity defaults 由 `data_interpretation_label_carriers.py` 承接。
- `InterpretationPreview` / `ValidationDecision`、candidate preview serialization 和 safe /
  needs-confirmation / blocked decision boundary 由 `data_interpretation_review.py` 承接。
- `ScanResult`、source scanning、source kind classification、BIDS root detection、label carrier
  discovery 和 scan warning / blocked reason assembly 由 `data_interpretation_scan.py` 承接。
- `InterpretationCandidate`、scan + user choices to candidate conversion、metadata override、
  event/class mapping 和 candidate recipe trace 由 `data_interpretation_candidate.py` 承接。
- UI / agent / headless / MCP 的 command name、capability policy 和 `CommandResult` contract
  沒有因拆分改變。

### Evidence 入口

- Detailed slice validation：`docs/records/worklog.md`
- Backend boundary description：`docs/architecture/backend.md`
- Current blockers：`docs/current.md`、`docs/planning/now.md`

### 不能宣稱完成

- `ApplicationService` 還保留 public compatibility wrapper methods；需要繼續確認 UI / agent / MCP
  沒有把 wrapper compatibility 誤當新產品心智模型。
- Legacy `load_data / attach_labels / import_labels` 尚未完全退出產品心智模型。
- 這是 backend architecture cleanup，不是 UI / Windows / MCP / thesis final closure。

### 下一手重點

1. 檢查 UI / agent / MCP 是否仍有 controller-private fallback 或 legacy wrapper path 進入產品主路徑。
2. 確認 UI / agent / MCP 沒有重新引入 controller-private fallback 作為產品主路徑。
3. 維持每個 slice 有 focused tests、non-mocked workflow regression 和文件同步。

## 2026-05-04 Product Completion Status Snapshot

### 狀態

Goal 1 baseline 已不再只是 backend baseline：Backend Command Spine、Data Interpretation
第一版產品路徑、local assistant runtime、tool-call benchmark、stdio MCP server、Windows
launcher command path、ChatPanel walkthrough 和 VisualizationPanel render 都已有可重跑 evidence。

這些進展仍是 product-completion baseline，不是最終成品 closure。完成度判斷要以
`docs/current.md`、`docs/planning/roadmap.md` 和 `docs/validation/README.md` 的 claim boundary
為準。

### 已可宣稱

| Track | 高層狀態 |
| --- | --- |
| Backend Command Spine | `ApplicationService / Command API` 已成為 UI、agent、headless、MCP 的主要 command spine；多個 legacy path 已降為 compatibility。 |
| Data Interpretation | 已有 scan -> preview -> validate -> confirm/apply -> save recipe 的第一版 UI / backend 主線；metadata、class map、event role、label carrier plan 和 format boundaries 可預覽與保存，reviewed subject/session 也會同步到 loaded data / Dataset table。 |
| Label / Event Import | reviewed timestamp labels、MAT / TXT trial-order sequence labels、窄版 MAT sample-anchor labels 已接進 Data Interpretation apply path；ambiguous mapping 會 blocked / skipped，不自動亂猜。 |
| UI Product Experience | ChatPanel 已從 debug dock 改成產品面板；有 true local-model 回覆、tool command、多輪、Data Interpretation chain、pipeline chain、training boundary / completion walkthrough artifacts，以及 consolidated automated human-like UI walkthrough。Walkthrough artifact 現在保存 per-phase visible text、button state、workflow/backend snapshots 和 UI quality review。Walkthrough-driven polish 已修 Data Interpretation density、Training plot readability / history header、Evaluation compact controls 和 ChatPanel reset stale UI。 |
| Agent / Local LLM | local primary / fallback 非中國模型已跑 `117` thesis-candidate tool-call cases，各 `3` 次，artifact 顯示 `117 / 117`，dashboard 已列 model comparison、case family、metric 和 failure taxonomy。 |
| Automation / MCP | real stdio MCP server 已存在，tool schema 來自同一套 ApplicationService automation truth；stdlib-only client walkthrough、official Inspector CLI `tools/list` 和 automated Inspector GUI click-through baseline 已保存。 |
| Launcher / Visualization | Windows launcher command walkthrough、startup geometry diagnostics、MainWindow VisualizationPanel Matplotlib render evidence 已保存。 |
| Docs / Validation | thesis evidence 已校正為 tool-call accuracy；validation docs 已明確區分 engineering baseline、UI-observable evidence 和不能宣稱的 release/thesis closure。 |

### Evidence 入口

- Current truth：`docs/current.md`
- Roadmap track status：`docs/planning/roadmap.md`
- Short-term blockers：`docs/planning/now.md`
- Validation boundaries：`docs/validation/README.md`
- Detailed slice log：`docs/records/worklog.md`
- Goal continuation / handoff：`artifacts/goal/`
- UI artifacts：`artifacts/ui/`
- MCP artifacts：`artifacts/mcp/`
- Launcher artifacts：`artifacts/launcher/`
- Agent eval artifacts：`artifacts/agent_evals/`
- Data Interpretation artifacts：`artifacts/data_interpretation/`

### 不能宣稱完成

- Data Interpretation 仍不是完整 mature import wizard：post-load label editor、raw trigger
  selector、complex GDF / MAT anchor reconciliation、XDF / LSL stream parser、全格式 real-data
  manual certification 都未完成。
- `load_data / attach_labels` legacy compatibility 仍存在；新 UI / agent 的核心心智模型已往
  Data Interpretation 移動，但尚未能宣稱 legacy model 完全退出。
- MCP 已有 real stdio server、client config、CLI walkthrough 和 automated Inspector GUI
  click-through；仍不能宣稱 HTTP transport、long-running training through MCP 或 full MCP client
  certification。
- Windows launcher 已有 automated command walkthrough；真人 Desktop click-through、packaging
  release approval 和多螢幕實際操作仍未完成。
- ChatPanel 已有多個 true local-model walkthrough；仍不能宣稱長時間 autonomous workflow、
  完整 UI-routing render 或完整 release walkthrough。
- VisualizationPanel Matplotlib tabs 已有 screenshot evidence；interactive desktop 3D / PyVista
  render 尚未驗證，headless 只支撐 blocked UX。
- Tool-call benchmark 已達 thesis-candidate case 數與 primary / fallback x3 重跑；這支撐
  tool-call benchmark claim，不等於整個桌面產品、UI usability 或論文實驗最終 closure。
- 最新使用者要求的 UI-observable human-like walkthrough 已形成單一 artifact，且 artifact 直接
  保存 visible text / button state / workflow snapshot / UI quality review；它仍不能替代真人
  Windows / 雙螢幕 / DPI desktop acceptance。

### 下一手重點

1. 收斂 Data Interpretation label editor / raw event anchor / XDF-LSL boundary，避免 wizard
   與 post-load compatibility path 形成雙主線。
2. 繼續依 consolidated walkthrough screenshots 做 UI polish；Data Interpretation density、
   Training plot readability / history header、analysis compact controls 和 ChatPanel reset stale UI
   已做第一輪，下一步聚焦 mature import wizard editor、assistant narrow/main-window layout 和整體產品感。
3. 做 Windows Desktop 真人 click-through；雙螢幕、DPI、launcher 與真長時間 local model session
   仍需 human desktop acceptance。
4. 補 interactive desktop 3D / PyVista render 驗證，或把 release boundary 寫得更明確。
5. 硬化 MCP HTTP / long-running tool-call boundary，不把 Inspector GUI baseline 擴張成 full
   MCP client certification。
6. 將 roadmap、current、validation 和 records 保持同步，但避免把 worklog 細節複製進
   implementation log。

## 2026-05-04 Backend Application Boundary Cleanup

### 狀態

`ApplicationService` 已完成第一個 god-object cleanup slice：Data Interpretation scan / preview /
validate / apply / recipe lifecycle state 和 handler logic 已移到
`DataInterpretationCommandService`，reviewed metadata / label carrier side effects 已移到
`DataInterpretationApplyService`。`ApplicationService` 仍是 UI、agent、headless、MCP 共用的
command dispatch、capability / confirmation gate 和 `CommandResult` envelope。

### 已可宣稱

- Data Interpretation lifecycle 和 reviewed apply side effects 不再由 `ApplicationService`
  直接管理。
- UI / agent / automation / MCP 仍透過同一個 `ApplicationService.execute()` command spine 進入，
  沒有新增 controller mutation fallback。
- 新 service 有 focused unit tests，既有 backend application / agent tool contract tests 仍通過。

### Evidence 入口

- Source：`XBrainLab/backend/application/data_interpretation_service.py`
- Source：`XBrainLab/backend/application/data_interpretation_apply.py`
- Boundary docs：`docs/architecture/backend.md`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是整個 backend architecture closure。Training、visualization、analysis、legacy
  `load_data / attach_labels / import_labels` compatibility handlers 仍需後續拆分與降權。
- Data Interpretation wizard 仍不是 mature embedded label editor；legacy post-load label import
  仍不能被包裝成新資料入口主線。

### 下一手重點

下一輪 backend work 應繼續把 `ApplicationService` 中剩餘大塊 workflow handlers 拆成 focused
services / handlers，同時保持 UI、agent、headless、MCP 只走同一套 command truth。

## 2026-05-05 Analysis Command Boundary Cleanup

### 狀態

`ApplicationService` 已完成第二個 backend boundary cleanup slice：`evaluate`、`visualize`、
`saliency` 和 confirmed `apply_montage` handler logic 已移到 `AnalysisCommandService`。
`ApplicationService` 仍是 command dispatch、capability / confirmation gate 和 result envelope。

### 已可宣稱

- Analysis / visualization readiness commands 不再由 `ApplicationService` 直接管理。
- Agent / UI / headless / MCP-facing command names 和 `CommandResult` contract 保持不變。
- 新 service 有 focused unit tests，既有 backend application / agent tool contract tests 仍通過。

### Evidence 入口

- Source：`XBrainLab/backend/application/analysis_service.py`
- Source：`tests/unit/backend/application/test_analysis_service.py`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這仍不是整個 backend architecture closure。後續 slices 已另外拆出 training、dataset
  generation、reset lifecycle、legacy compatibility、data-table、preprocess 和 state/query
  handlers；目前剩餘重點見本日最上方 backend command boundary cleanup snapshot。

### 下一手重點

下一輪 backend work 應確認新 UI / agent 心智模型不回到舊 `load_data / attach_labels`，並檢查
UI / agent / MCP 是否仍有產品主路徑旁路。
