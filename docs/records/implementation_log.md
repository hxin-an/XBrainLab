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

## 2026-05-05 Backend Command Boundary Cleanup

### 狀態

Backend command spine 持續從 `ApplicationService` god object 收斂成 focused command services。
Data Interpretation、analysis / visualization、training config / train-stop lifecycle、dataset
generation / split audit、reset lifecycle 現在都有各自 service boundary，`ApplicationService`
回到 dispatch、capability / confirmation gate 和 state/result envelope。

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
- UI / agent / headless / MCP 的 command name、capability policy 和 `CommandResult` contract
  沒有因拆分改變。

### Evidence 入口

- Detailed slice validation：`docs/records/worklog.md`
- Backend boundary description：`docs/architecture/backend.md`
- Current blockers：`docs/current.md`、`docs/planning/now.md`

### 不能宣稱完成

- `ApplicationService` 仍保留 query state 和 legacy data / label compatibility handlers。
- Legacy `load_data / attach_labels / import_labels` 尚未完全退出產品心智模型。
- 這是 backend architecture cleanup，不是 UI / Windows / MCP / thesis final closure。

### 下一手重點

1. 隔離 legacy compatibility path，並評估 `query_state` 是否需要獨立 query service。
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

- 這仍不是整個 backend architecture closure。Training configuration / train lifecycle、dataset
  generation rollback、reset lifecycle、legacy `load_data / attach_labels / import_labels`
  compatibility handlers 還在 `ApplicationService`。
- `query_state` 仍在 `ApplicationService`；它目前是 cross-cutting state / capability query，
  後續若拆分必須避免建立第二套 state truth。

### 下一手重點

下一輪 backend work 應優先隔離 legacy data / label compatibility handlers，避免新 UI / agent
心智模型回到舊 `load_data / attach_labels`。
