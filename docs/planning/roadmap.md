# XBrainLab Roadmap

最後更新：`2026-05-05`

這份 roadmap 定義 XBrainLab 走向工程級成品的產品主線。

它不是短期 task list，也不是歷史流水帳：

- 目前真相看 `docs/current.md`。
- 短期施工焦點看 `docs/planning/now.md`。
- 目標態看 `docs/target/`。
- 已做過的重要變更看 `docs/records/implementation_log.md`。

Roadmap 只回答一件事：XBrainLab 要完成成品，還必須打通哪些主線，以及每條主線怎樣才算完成。

## Product North Star

XBrainLab 的目標是成為可直接在本地使用的 EEG / BCI 分析桌面軟體。

使用者理想上只需要：

```text
提供資料位置
  -> 系統可靠解讀資料與 label / event
  -> 使用者確認不明確語意
  -> 軟體可完成 preprocessing / dataset / training / evaluation / visualization / saliency
  -> assistant 能在同一套 workflow truth 上協助操作
  -> external agents 可透過 MCP adapter 操作同一套 workflow truth
  -> 所有重要判斷都有可重跑 evidence
```

這代表 XBrainLab 不是 demo，不是只修到測試過關，也不是把聊天框接到幾個 controller。
完成品必須同時滿足：使用者友善、架構乾淨、資料語意可信、agent tool-call 可驗證、Windows
本地啟動可交付。

## 路線原則

- 對外只看完成品；工程內部可以切片，但不能把切片完成說成產品完成。
- UI、in-app agent、headless runner、MCP server 必須共用同一套 `ApplicationService / Command API`。
- 資料入口的核心不是舊 `load_data / attach_labels`，而是 Data Interpretation System。
- agent 不能靠 prompt 自己猜 backend 能力；可執行 command 必須由 backend capability policy 控制。
- MCP 是 external agent adapter，不是另一套 backend，也不能繞過 autonomy policy。
- 論文主 evidence 是 agent tool-call 準確率，不是 EEG training accuracy。
- local assistant runtime 是產品路線；不使用 API / Gemini 作為產品 execution path。
- 不使用中國公司或中國來源模型。
- dashboard clean 只能代表工程健康，不能代表產品、agent 或論文 claim 已完成。
- 文件、程式、測試、artifact 必須同步；不能留下多套 truth。

## 2026-05-05 Progress Snapshot

這是目前可掃描的產品進度，不是 goal complete 宣告。

### 已完成 Baseline

- Backend Command Spine：`ApplicationService / Command API` 已是 UI、agent、headless、
  MCP 的主要 workflow spine；core commands、typed result、capability policy、state
  snapshot 和 automation envelope 已有測試覆蓋。最新 backend cleanup 已把 Data
  Interpretation lifecycle handler 從 `ApplicationService` 拆到
  `DataInterpretationCommandService`，並把 reviewed metadata / label carrier side effects 拆到
  `DataInterpretationApplyService`；analysis / visualization handlers 也已拆到
  `AnalysisCommandService`；training config / train-stop lifecycle / history cleanup 也已拆到
  `TrainingCommandService`；dataset generation / split audit / cleanup 也已拆到
  `DatasetGenerationCommandService`；reset lifecycle 也已拆到 `LifecycleCommandService`。
  舊 `load_data` / `attach_labels` / `import_labels` compatibility 也已隔離到
  `DataCompatibilityCommandService`；metadata update / smart parse / remove files 也已拆到
  `DataTableCommandService`；preprocessing operations / `create_epoch` 也已拆到
  `PreprocessCommandService`；state snapshot assembly / `query_state` diagnostics 也已拆到
  `StateSnapshotService` / `QueryStateCommandService`。
  這是 god-object cleanup 的前幾步，不是後端全面完成。
- Data Interpretation 第一版主線：file / folder / BIDS-style / recipe flow 已可走
  scan -> preview -> validate -> confirm/apply -> save recipe；metadata、class map、event
  role、label carrier、format boundary 和 recipe trace 已進 UI / backend / state snapshot。
- Label carrier apply：reviewed timestamp CSV / TSV / BIDS events、MAT / TXT trial-order
  sequence、窄版 MAT sample-anchor labels 已可透過 Data Interpretation apply path 套用；ambiguous
  mapping 會 blocked / skipped，不自動猜。
- ChatPanel local assistant：true local model 已有 one-turn、tool command、multi-turn、
  Data Interpretation chain、pipeline chain、training readiness / completion walkthrough artifacts；
  visible transcript 不應暴露 raw tool syntax。
- Tool-call benchmark：`117` thesis-candidate cases，primary
  `microsoft/Phi-4-mini-instruct` 和 fallback `microsoft/Phi-3.5-mini-instruct` 各 `3` 次，
  artifact 顯示 `117 / 117`，並有 dashboard breakdown。這支撐 tool-call benchmark claim，
  不等於產品 release closure。
- MCP baseline：real stdio MCP server、stdlib-only client walkthrough、Inspector-compatible
  Windows WSL config、official Inspector CLI `tools/list` artifact 和 Inspector GUI
  click-through artifact 已存在。
- Launcher / visualization baseline：Windows launcher automated command walkthrough、
  startup geometry diagnostics、VisualizationPanel Matplotlib render screenshots 已存在。

### 尚未完成 Product Closure

- Windows Desktop 真人 click-through、packaging release approval 和雙螢幕實際操作仍未完成。
- Data Interpretation 還缺 mature embedded label editor、raw trigger selector、complex
  GDF / MAT anchor reconciliation、XDF / LSL stream parser 和全格式 real-data manual certification。
- `load_data / attach_labels` 仍作為 legacy compatibility path 存在；不能宣稱已完全退出心智模型。
- interactive desktop 3D / PyVista render 未驗證；目前只支撐 headless blocked UX。
- 長時間 autonomous ChatPanel workflow、完整 release walkthrough 和 UI-routing render 仍未完成。

## Product Completion Tracks

| Track | 目標 | 目前判斷 | 完成條件 |
| --- | --- | --- | --- |
| Documentation Truth | 文件能讓人掌握目標、現況、決策與驗證證據。 | canonical 結構已建立；implementation log 已改為高層狀態，worklog 保留細節。仍需持續避免 current / now / roadmap 分岔。 | `target/`、`architecture/`、`planning/`、`validation/`、`records/` 分工穩定；MkDocs strict 通過；文件不再宣稱未完成能力。 |
| Backend Command Spine | UI / agent / script 都走同一套 workflow command layer。 | 主要 spine 已落地：UI actions、agent mapped tools、headless automation、MCP stdio calls 都已大幅收斂到 `ApplicationService`。Data Interpretation lifecycle、analysis / visualization handlers、training config / train-stop lifecycle、dataset generation / split audit、reset lifecycle、legacy data / label compatibility、metadata table mutation、preprocess / epoch handlers、state snapshot / query diagnostics 已拆到 focused services；`ApplicationService` 主要保留 dispatch、capability / confirmation gate、result envelope 和 compatibility wrappers。 | 核心 workflow 不再靠 UI/controller 私有邏輯；command、state snapshot、capability policy、typed result、confirmation、rollback 都有 non-mocked tests；`ApplicationService` 不再承擔所有 workflow 細節。 |
| Data Interpretation System | 使用者給資料位置，系統建立可預覽、可驗證、可重跑的 `DataInterpretation`。 | 第一版產品主線已可用並有 UI-observable artifact；label carrier plan、format boundaries、metadata、class map、event role、recipe trace 已進 UI / backend / state snapshot，reviewed subject/session 也會同步到 loaded data 與 Dataset table。仍不是完整 mature wizard。 | `scan -> interpret -> preview -> validate -> confirm -> apply -> recipe` 成為 UI / agent / headless 的唯一資料入口心智模型；legacy label/import path 只保留 compatibility。 |
| UI Product Experience | 使用者看到的是 EEG workflow 工具，不是 debug 面板。 | ChatPanel、Data Interpretation wizard、VisualizationPanel、launcher command path 和 consolidated automated human-like walkthrough 都有 product evidence；walkthrough artifact 現在 top-level 保存 visible text、button state、workflow/backend snapshot 和 UI quality review。Walkthrough-driven polish 已修 Data Interpretation density、Training plot readability / history header、Evaluation compact controls 和 ChatPanel reset stale UI。仍缺真人 Windows click-through、mature import wizard editor 和完整 narrow layout polish。 | import、preprocess、dataset、training、evaluation、visualization、saliency、assistant 都能被正常操作；狀態與錯誤用使用者語言呈現。 |
| Agent Runtime And Tool Surface | assistant 是 workflow operator，透過 state、verification 和 command result 操作軟體。 | local model walkthroughs 和 `117` case tool-call benchmark 已支撐 thesis-candidate benchmark claim；長時間 autonomous workflow、UI-routing 和 full recovery behavior 仍未 closure。 | agent tools 遷移到 Data Interpretation + ApplicationService command；State Snapshot、Verification Result、visible response、retry / recovery 都可評分。 |
| Automation Adapters / MCP | CI、eval、batch 和外部 agent 能操作同一套 workflow truth。 | real stdio MCP server、stdlib-only client walkthrough、Inspector config、official Inspector CLI baseline 和 automated Inspector GUI click-through 已完成；HTTP transport、long-running training through MCP 和 full MCP client certification 仍未完成。 | CLI/headless runner 用於 CI / eval / batch；MCP server 暴露同一套 command taxonomy 給 external agents；client 不需安裝 XBrainLab 的 EEG/PyQt/PyTorch 依賴；所有 MCP calls 仍受 capability / autonomy policy 約束。 |
| Validation And Thesis Evidence | 以可重跑 benchmark 證明 agent tool-call 準確率。 | `117` thesis-candidate cases、primary / fallback x3 local rerun 已完成並顯示 `117 / 117`，dashboard 已列 case family、metric、failure taxonomy 和 model comparison；這是 tool-call benchmark evidence，不是整個產品 release evidence。 | benchmark case schema、scorer、runner、artifact、failure taxonomy 和 report 可重現；UI / launcher / MCP / import wizard evidence 不能被 benchmark 分數取代。 |
| Packaging And Release | 使用者能從 Windows 桌面啟動並可靠使用。 | Desktop command / PowerShell launcher automated walkthrough、startup geometry diagnostics 已完成；真人 click-through、packaging release approval 和多螢幕實際驗收仍未完成。 | Desktop launcher / packaging、local model consent、資源提示、geometry recovery、真 Windows walkthrough、release gate 全部通過。 |

## Roadmap Order

這不是版本承諾，而是從目前 baseline 往成品 closure 推進的順序：

1. **維持文件真相**
   - `implementation_log.md` 只保留高層狀態；細節驗證寫在 `worklog.md`。
   - 每次產品 track 狀態變化後，同步 `current.md`、`now.md`、`roadmap.md` 和
     `validation/README.md`。

2. **清乾淨 Legacy Command 心智模型**
   - 持續拆分 `ApplicationService`：新 workflow 不再直接塞進 service god object，而是放進
     focused command service / handler。
   - 新 UI / agent 的資料入口繼續以 Data Interpretation 為主。
   - `load_data / attach_labels` 只保留 service-backed compatibility，不可再成為 primary
     workflow language。
   - 繼續盤點 UI / agent 是否還有 controller-private bypass。

3. **把 Data Interpretation 從 Baseline Wizard 硬化成 Mature Import Wizard**
   - 補 embedded label editor、raw trigger selector、anchor reconciliation 和更清楚的
     blocked / needs-confirmation UX。
   - 對 BIDS、GDF external labels、MAT / CSV / TSV labels、EEGLAB、BrainVision、EDF annotations、
     XDF / LSL、自建資料 fallback 建立更完整的 user-facing capability boundary。
   - 所有 recipe reload 都要重新 preview / validate，且 UI 明確顯示差異。

4. **完成 UI Product Walkthrough**
   - consolidated automated human-like replay 已覆蓋 import -> preprocess -> epoch -> dataset ->
     training readiness -> evaluation / visualization / saliency readiness。
   - button-driven full train -> evaluate -> visualization / saliency render 還需要後續 polish /
     validation。
   - ChatPanel assistant-driven workflow 要能以使用者語言完成代表性流程，不暴露 raw tool
     syntax、schema 或 traceback。
   - Windows Desktop click-through、main window geometry、多螢幕與 loading 狀態需要真驗收。

5. **硬化 Agent Autonomy / Recovery**
   - 繼續讓 Context Assembler 只暴露 backend policy 允許或需要確認的 command。
   - 每一步都經 Verification Layer、capability policy、autonomy decision，並一次只執行一個
     verified command。
   - missing input、blocked、needs confirmation 和 recovery 要能在 UI 裡用人話回覆。

6. **完成 Automation Adapters / MCP 驗收**
   - 保留 CLI / headless runner 作為 CI、eval、batch 和 artifact 入口。
   - MCP Inspector GUI click-through 已有 screenshot / visible text / connected tools evidence；
     後續要補 HTTP / long-running MCP tool-call boundaries。
   - MCP tools 繼續使用同一套 Data Interpretation / command taxonomy，不直接操作 controller。
   - MCP client 不需要下載 XBrainLab 的大型科學計算與 UI 依賴；依賴留在 XBrainLab prepared runtime。

7. **把 Tool-call Benchmark 轉成 Thesis Report Evidence**
   - 目前 `117` cases x primary/fallback x3 是 benchmark evidence。
   - 下一步要整理 score breakdown、failure taxonomy、case coverage 和重跑 protocol，避免只用
     pass rate 當報告。
   - benchmark 不能取代 UI / launcher / MCP / import wizard evidence。

8. **完成 Product Walkthrough And Release Gate**
   - Windows launcher 真機 click-through。
   - 真 local model ChatPanel 長鏈 walkthrough。
   - button-driven UI 和 assistant-driven workflow 都要能走完代表性流程。
   - 測試、文件、artifact、launcher / packaging 全部同步後才可稱為可交付。

## Non-goals

- 不把 roadmap 寫成每天要做什麼；短期工作放 `now.md`。
- 不用更多 planning 文件分散 truth。
- 不把舊 `load_data / attach_labels` 當成新產品資料入口。
- 不把 mock-heavy tests 當成真實 workflow evidence。
- 不把 scripted replay 的文字報告當成 UI 行為已驗證；需要 transcript、state、screenshot 或
  UI observable artifact。
- 不把 EEG model accuracy 寫成本論文主 evidence。
- 不下載超過資源邊界的大模型；單模型原則 10GB 內，總 cache 原則 20GB 內，除非使用者明確同意。
- 不讓 API / Gemini / remote LLM 回到產品 execution path。
- 不讓 MCP 成為第三套 workflow truth 或繞過 ApplicationService。

## 成品判定

XBrainLab 只有在下列條件同時成立時，才算進入可交付狀態：

- 使用者可以從 Windows 桌面啟動。
- UI 能完成代表性 EEG workflow。
- assistant 能在同一套 backend truth 上協助操作，而不是暴露 raw tool / debug syntax。
- external agents 能透過 MCP 操作同一套 command surface，而不需要自己安裝 XBrainLab 的完整
  EEG/PyQt/PyTorch stack。
- 資料匯入與 label / event 解讀可預覽、可確認、可保存 recipe、可重跑。
- training / evaluation / visualization / saliency 可以追溯資料 recipe 與 workflow state。
- tool-call eval 有固定 cases、重跑 artifact、score breakdown 和 failure taxonomy。
- 文件與程式碼一致，沒有把未完成能力寫成已完成。
