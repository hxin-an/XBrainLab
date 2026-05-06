# XBrainLab Roadmap

最後更新：`2026-05-06`

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

## 2026-05-06 Progress Snapshot

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
  `StateSnapshotService` / `QueryStateCommandService`。UI runtime bypass audit 已修 Dataset direct
  import、Preprocess reset、Training re-split dataset cleanup 和 Clear History 的
  service-success controller fallback。Data Interpretation format capability taxonomy 也已從大型
  lifecycle module 抽到 focused `data_interpretation_formats.py`；metadata resolution / BIDS
  summary 也已抽到 `data_interpretation_metadata.py`；recipe serialization 也已抽到
  `data_interpretation_recipe.py`；label carrier planner 也已抽到
  `data_interpretation_label_carriers.py`；preview / validation review boundary 也已抽到
  `data_interpretation_review.py`；source scanner / source classification 也已抽到
  `data_interpretation_scan.py`；candidate builder / metadata override 也已抽到
  `data_interpretation_candidate.py`；Data Interpretation lifecycle stores、latest-id resolver、
  snapshot assembly、clear 和 label-import recipe state 也已抽到
  `data_interpretation_state.py`。仍需繼續盤點其餘 UI runtime mutating paths。
  最新 read-side guard 也把 AgentManager montage channel choices 和 PreprocessPlotter
  original-data overlay 改成 query-backed state / data-list source；direct
  `study.epoch_data` / `study.loaded_data_list` product UI reads 現在會被 architecture compliance
  擋下，除非它們被隔離在 explicit legacy fallback helpers。這是 god-object cleanup 的前幾步，
  不是後端全面完成。
- Data Interpretation 第一版主線：file / folder / BIDS-style / recipe flow 已可走
  scan -> preview -> validate -> confirm/apply -> save recipe；metadata、class map、event
  role、label carrier、format boundary 和 recipe trace 已進 UI / backend / state snapshot。label
  carrier review 和 event role review 已改用 selector controls，replay artifact 會保存
  `event_rows` / `label_carrier_rows`。Recipe reload 現在也會 rehydrate saved choices 再
  preview / validate，不再只靠 source path 重建空 candidate；automated walkthrough 也會截取
  reload preview dialog。
- Label carrier apply：reviewed timestamp CSV / TSV / BIDS events、MAT / TXT trial-order
  sequence、窄版 MAT sample-anchor labels 已可透過 Data Interpretation apply path 套用；ambiguous
  mapping 會 blocked / skipped，不自動猜。
- ChatPanel local assistant：true local model 已有 one-turn、tool command、multi-turn、
  Data Interpretation chain、pipeline chain、training readiness / completion walkthrough artifacts；
  visible transcript 不應暴露 raw tool syntax。
- Tool-call benchmark：deterministic suite 已到 `121` cases，包含 recipe reload
  `eeg_file_remap` / `label_carrier_remap` 和 missing remap target clarification；
  deterministic、primary `microsoft/Phi-4-mini-instruct` 和 fallback
  `microsoft/Phi-3.5-mini-instruct` artifact 都已更新為 `121 / 121`，local models 各重跑 `3`
  次，並有 dashboard breakdown。scorer 已收緊 blocked intent 下的替代 tool
  判定，direct blocked command 只算 verifier/capability-policy boundary，不算執行成功。這支撐
  已重跑 benchmark slice，不等於產品 release closure。
- Agent data-entry mental model：Empty / Data Loaded / Preprocessed stage prompt 不再曝光
  `load_data / attach_labels` 作為 primary tools；Context Assembler 會把 backend capability
  policy 與 stage allowlist 取交集，讓 Data Interpretation 成為 agent 的資料入口主語言。
- Automation / MCP data-entry taxonomy：headless command specs 和 MCP `tools/list` metadata
  會把 `load_data` / `attach_labels` / `import_labels` 標成 legacy compatibility、非 primary
  workflow，並指向 Data Interpretation preferred commands。
- MCP baseline：real stdio MCP server、stdlib-only client walkthrough、Inspector-compatible
  Windows WSL config、official Inspector CLI `tools/list` artifact、Inspector GUI
  click-through artifact 和 local HTTP transport / train job walkthrough 已存在。
- Launcher / visualization baseline：Windows launcher automated command walkthrough、
  startup geometry diagnostics、VisualizationPanel Matplotlib render screenshots 已存在。

### 尚未完成 Product Closure

- Windows Desktop 真人 click-through、packaging release approval 和雙螢幕實際操作仍未完成。
- Backend command spine 已大幅改善，但仍只能宣稱 partially aligned：UI refresh 仍有
  observer event、manual panel refresh、tab switch refresh、command-result local refresh 和
  ChatPanel / agent signal path 的混合模式。第一個 coordinator slice 已把 real `Study`
  command result refresh 集中到 `refresh_after_command()`，但 product runtime mutating path
  還需要完整 audit，確認不 silent fallback 到 controller mutation。2026-05-05 reviewer finding
  將此維持為 product-completion follow-up，不阻塞目前 validation / local eval closure，但
  product-complete 前不可宣稱 target architecture 已 fully aligned。
- Data Interpretation 還缺 mature embedded label editor、raw trigger selector、complex
  GDF / MAT anchor reconciliation、XDF / LSL stream parser 和全格式 real-data manual certification。
- `load_data / attach_labels` 仍作為 legacy compatibility path 存在；agent primary stage
  prompts 和 MCP/headless schema 已降權它們，但 UI post-load label compatibility 仍需繼續盤點，
  不能宣稱已完全退出產品心智模型。
- interactive desktop 3D / PyVista render 未驗證；目前只支撐 headless blocked UX。
- 長時間 autonomous ChatPanel workflow、完整 release walkthrough 和 UI-routing render 仍未完成。

## Product Completion Tracks

| Track | 目標 | 目前判斷 | 完成條件 |
| --- | --- | --- | --- |
| Documentation Truth | 文件能讓人掌握目標、現況、決策與驗證證據。 | canonical 結構已建立；implementation log 已改為高層狀態，worklog 保留細節。仍需持續避免 current / now / roadmap 分岔。 | `target/`、`architecture/`、`planning/`、`validation/`、`records/` 分工穩定；MkDocs strict 通過；文件不再宣稱未完成能力。 |
| Backend Command Spine | UI / agent / script 都走同一套 workflow command layer。 | 主要 spine 已落地：UI actions、agent mapped tools、headless automation、MCP stdio calls 都已大幅收斂到 `ApplicationService`。Data Interpretation lifecycle、analysis / visualization handlers、training config / train-stop lifecycle、dataset generation / split audit、reset lifecycle、legacy data / label compatibility、metadata table mutation、preprocess / epoch handlers、state snapshot / query diagnostics 已拆到 focused services；Dataset direct import、Preprocess operation / reset、Training re-split cleanup 和 Clear History 的 service-success controller fallback 已修；Data Splitting dialog、Training history query-none render fallback、Stop Training / Clear History / Preprocess Reset / Dataset Clear / Channel Selection apply / Generate Dataset apply / Data Splitting clear / Data Splitting context / Model Selection / Training Settings / Start Training / Remove Files / Metadata Update / Dataset inline Metadata / Smart Parse Apply / Smart Parse Filename / Label Import / Direct Load compatibility / AgentManager montage fallback warning、Evaluation stale-selection fallback、Evaluation/Preprocess panel render source、Preprocess plotter render source、Visualization failed-query / query-none / average stale-selection fallback、Visualization setup/export fallback warning、post-load label target fallback，以及 DatasetPanel query-none render fallback 與 Dataset/Preprocess query-unavailable dialog/render fallback 也已收斂，避免 real `Study` render / dialog / compatibility label path 回讀 stale controller list 或外拋 legacy fallback exception；architecture guard 也開始覆蓋 stale render fallback，要求 `result is None` controller render reads 必須走 explicit legacy wrapper；read-side architecture guard 現在也覆蓋 direct mutable Study state reads，AgentManager montage picker 和 PreprocessPlotter original overlay 已改走 `QueryStateCommand` / data-list query；`apply_interpretation` capability 現在也套用 raw-edit blockers，避免 agent/MCP 在已有 downstream state 時套用新資料；`ApplicationService` 主要保留 dispatch、capability / confirmation gate、result envelope 和 compatibility wrappers。UI refresh coordinator first slice 已建立，real `Study` `execute_application_command()` 會依 `CommandResult.changed_state` 刷新主要 workflow panels / info / assistant status；Training readiness、Dataset smart-parse / metadata / remove-files refresh、Data Interpretation import/apply / recipe reload refresh、post-load label compatibility service-success refresh、direct load compatibility service-success refresh、Dataset sidebar channel-selection / clear-dataset refresh、Dataset inline metadata refresh、Preprocess sidebar operation/reset refresh，以及 Visualization montage/saliency refresh 已開始交回 coordinator。仍不能宣稱 fully aligned：observer/manual refresh 與剩餘 mutating UI fallback 仍需 audit。 | 核心 workflow 不再靠 UI/controller 私有邏輯；command、state snapshot、capability policy、typed result、confirmation、rollback 都有 non-mocked tests；`ApplicationService` 不再承擔所有 workflow 細節；UI refresh 由 centralized coordinator 根據 `CommandResult.changed_state` 驅動，product runtime 不 silent fallback 到 controller mutation。 |
| Data Interpretation System | 使用者給資料位置，系統建立可預覽、可驗證、可重跑的 `DataInterpretation`。 | 第一版產品主線已可用並有 UI-observable artifact；Dataset sidebar 現在明確提供 EEG file(s)、folder/BIDS root 和 saved recipe 三個入口。label carrier plan、format boundaries、metadata、class map、event role、recipe trace 已進 UI / backend / state snapshot，reviewed subject/session 也會同步到 loaded data 與 Dataset table。Format capability taxonomy、metadata resolution、recipe serialization、label carrier planner、preview / validation review boundary、source scanner、candidate builder 和 session-state snapshot boundary 已抽成 focused modules。Wizard review surface 已改用 structured `Review Summary`，label carrier / event role review 已改成 selector controls，recipe reload 已會 rehydrate saved choices 並顯示 matched / changed rows；saved recipe selected EEG 或 label/event carrier missing from rescan now blocks before apply，explicit EEG file / label carrier remap 已支援到 wizard selector / re-preview / re-validate。最新 table-fit polish 已讓 metadata、label / event / recipe trace 和 review summary table 依 viewport 重算欄寬並用 elide 防 overflow；latest selector-fit polish 又讓 target file 以 compact `sub-01 run-2` 顯示、`Needs review` 不截斷，同時 recipe/apply 仍保存完整 filename。但這仍不是完整 mature wizard。 | `scan -> interpret -> preview -> validate -> confirm -> apply -> recipe` 成為 UI / agent / headless 的唯一資料入口心智模型；legacy label/import path 只保留 compatibility。 |
| UI Product Experience | 使用者看到的是 EEG workflow 工具，不是 debug 面板。 | ChatPanel、Data Interpretation wizard、VisualizationPanel、launcher command path 和 consolidated automated human-like walkthrough 都有 product evidence；walkthrough artifact 現在 top-level 保存 visible text、button state、workflow/backend snapshot 和 UI quality review，且 ChatPanel visible text snapshot 會包含 chat bubble text，不再只靠 screenshot 證明 clarification / blocked / success messages 可見。Walkthrough-driven polish 已修 Data Interpretation density、Review Summary table、event role selector、Training plot readability / history header、Evaluation compact controls 和 ChatPanel reset stale UI；Start Training button 已補 long-running confirmation artifact；Dataset source-entry options 已補 file / folder-BIDS / recipe sidebar artifact。最新 Dataset artifact 顯示 table 欄位以 proportional interactive widths 填滿主 panel，preview/remap dialog table header 也填滿容器且不水平外溢；human-like walkthrough 也把 `15` 個 table/tree widget geometry 納入 UI quality gate，目前 `0` geometry findings、`0` clipped-row findings。`Events` / `Labels` 語意已分開且不再用綠色把 external labels 標成成功狀態；`Channel Selection` 也已從 success-green 改為中性 action，避免把會修改資料的操作誤呈現成成功狀態；`Clear Dataset` 也在 empty startup / reset 後 disabled、用中性 disabled styling 和 `No dataset to clear.` tooltip，只有實際有 clearable state 時才 enabled。preview dialog 底部 confirmation copy 已改成短 action cue，細節保留在 `Review Summary`。最新 eval dashboard screenshot 也已改成 dark styled report，且第一屏顯示 claim boundary，不再把 raw Markdown pipe tables 或孤立 100% 分數當作產品 evidence。仍缺真人 Windows click-through、mature import wizard editor 和完整 narrow layout polish。 | import、preprocess、dataset、training、evaluation、visualization、saliency、assistant 都能被正常操作；狀態與錯誤用使用者語言呈現。 |
| Agent Runtime And Tool Surface | assistant 是 workflow operator，透過 state、verification 和 command result 操作軟體。 | local model walkthroughs 和 `121` case local tool-call benchmark 已支撐該 benchmark slice；最新 suite 補 recipe reload `eeg_file_remap` / `label_carrier_remap` / missing remap target clarification，且 `preview_interpretation` schema 已與 headless/MCP 共用；primary / fallback local models 各 `3` 次都為 `121 / 121`。stage prompt / tool exposure 已把 legacy data entry 降權，Data Interpretation 是 primary data-entry language；real `Study` mapped workflow tools 若缺參數不能組成 ApplicationService command，現在會回 structured input failure，不退回 legacy execution；長時間 autonomous workflow、UI-routing 和 full recovery behavior 仍未 closure。 | agent tools 遷移到 Data Interpretation + ApplicationService command；State Snapshot、Verification Result、visible response、retry / recovery 都可評分。 |
| Automation Adapters / MCP | CI、eval、batch 和外部 agent 能操作同一套 workflow truth。 | real stdio MCP server、stdlib-only client walkthrough、Inspector config、official Inspector CLI baseline、automated Inspector GUI click-through 和 local HTTP transport / train job baseline 已完成；MCP/headless schema 已標出 legacy data-entry compatibility boundary；Data Interpretation preview choices schema 現在共用 `data_interpretation_choice_schema.py`，所以 MCP / headless / agent 都看得到 recipe remap choices；`tools/call` structured result 現在含 headless adapter/session metadata，避免誤宣稱 desktop UI refresh；stdio `train` 仍保留 backend precondition truth 並拒絕同步長任務，HTTP `train` 會建立 in-memory job，可查 status / progress snapshot 並 cancel，且同 session duplicate start 會回 `job_already_running`，terminal job status 不會被後續 run 改寫；evaluation / visualization jobs、job persistence / recovery、remote authorization certification 和 full MCP client certification 仍未完成。 | CLI/headless runner 用於 CI / eval / batch；MCP server 暴露同一套 command taxonomy 給 external agents；client 不需安裝 XBrainLab 的 EEG/PyQt/PyTorch 依賴；所有 MCP calls 仍受 capability / autonomy policy 約束。 |
| Validation And Thesis Evidence | 以可重跑 benchmark 證明 agent tool-call 準確率。 | deterministic、primary 和 fallback artifact 都已刷新為 `121 / 121`，含 recipe remap family；primary / fallback 各重跑 `3` 次。dashboard 已列 case family、metric、failure taxonomy 和 model comparison；fallback x3 已記錄 VRAM / latency resource pressure。這是 tool-call benchmark evidence，不是整個產品 release evidence，也不是日常小修 gate。 | benchmark case schema、scorer、runner、artifact、failure taxonomy、resource preflight 和分層 gate policy 可重現；UI / launcher / MCP / import wizard evidence 不能被 benchmark 分數取代。 |
| Packaging And Release | 使用者能從 Windows 桌面啟動並可靠使用。 | Desktop command / PowerShell launcher automated walkthrough、startup geometry diagnostics 已完成；真人 click-through、packaging release approval 和多螢幕實際驗收仍未完成。 | Desktop launcher / packaging、local model consent、資源提示、geometry recovery、真 Windows walkthrough、release gate 全部通過。 |

Latest Data Interpretation UI polish: the wizard `Review Summary` now renders recipe trace tokens as
user-facing rows such as `Source scan`, `Metadata choices`, `Event role choices`, and `Label import`;
raw trace tokens remain in backend diagnostics. This is a completed UI readability slice inside the
Data Interpretation track, not mature recipe diff / import-wizard closure. The Data Interpretation
replay artifact now also has a visible-text guard for raw command / recipe trace token leakage.

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
   - `load_data / attach_labels` 只保留 service-backed compatibility；agent stage prompt 和
     MCP/headless schema 已降權，後續要繼續檢查 UI language 不再把它們當 primary workflow
     language。
   - 繼續盤點 UI / agent 是否還有 controller-private bypass。

3. **UI Command Refresh Coordinator + Controller Fallback Audit**
   - First slice 已建立 centralized UI refresh coordinator helper；real `Study`
     `execute_application_command()` 會根據 `CommandResult.changed_state` 刷新 dataset /
     preprocess / training / analysis / assistant status / capability state。
   - Training sidebar fallback audit slice 已新增 explicit mock / legacy-only fallback helper；
     split cleanup / generate dataset、model selection、training settings、start / stop training 和
     clear history 不會在 real `Study` context 下 silent fallback 到 controller mutation；latest
     follow-up 也把 no-capability readiness / split / configuration / stop / clear-history
     preflight reads 收進同一 helper，real `Study` 會 blocked / unavailable 而不是回讀 stale
     controller truth。
   - Preprocess sidebar fallback audit slice 已用同一 helper 收斂 filter / resample / rereference /
     normalize / epoch / reset fallback；latest follow-up 也把 no-capability lock/data preflight
     reads 收進 helper，real `Study` 不再用 stale `PreprocessController.is_epoched()` /
     `has_data()` 決定 preprocess action gating。
   - Dataset fallback audit slice 已用同一 helper 收斂 metadata edit / batch metadata、smart parse、
     remove files、direct file import、clear dataset、channel selection 和 post-load label compatibility
     fallback；latest follow-up 也把 Dataset sidebar no-capability lock/data render and
     channel-selection preflight reads 收進 helper，real `Study` 不再用 stale
     `DatasetController.is_locked()` / `has_data()` 決定 button state 或 action gating；latest
     action-handler follow-up 也清掉 file import、folder/BIDS source flow 和 Smart Parse 的
     no-capability controller lock/data preflight reads。
   - Visualization / AgentManager fallback audit slice 已用同一 helper 收斂 saliency settings 和
     assistant montage confirmation fallback。
   - Read-side Study state guard 已納入 architecture compliance：product UI 不可直接讀
     `study.epoch_data` / `study.loaded_data_list` 這類 mutable Study state；AgentManager montage
     picker 和 PreprocessPlotter original overlay 已改用 state / data-list query，legacy reads 只留在
     explicit fallback helper。
   - Direct Study controller lookup guard 也已納入 architecture compliance：五個 workflow panel
     constructor 和 AgentManager 不再把 `parent.study.get_controller(...)` /
     `study.get_controller(...)` 當 real `Study` fallback；MainWindow injection 是 product wiring
     truth，legacy lookup 只留在 explicit helper。
   - `tests/architecture_compliance.py` 現在會守住這條 boundary：missing command result branch 不可
     直接呼叫 controller mutation，必須走 explicit mock / legacy-only fallback helper。
   - 最新 architecture guard hardening 也讓 no-capability branch 不能直接呼叫 controller
     readiness methods；controller readiness fallback 必須放進 explicit legacy helper。
   - 最新 observer-handler guard 也要求 known refresh events 的 callback-specific handlers 呼叫
     `refresh_after_observer()`；event handler 可以先做 log / plot / local side effect，但不可
     停在局部 refresh。
   - 後續要把剩餘 observer/manual/tab-switch refresh 收斂到同一 truth，避免 action handler 自己
     持續猜刷新範圍。
   - Data Interpretation import/apply 與 recipe reload apply 的 service-success local refresh 已移除；
     這些 path 現在依 `ApplyInterpretationCommand.changed_state` 交給 coordinator。
   - post-load label compatibility service-success local refresh 已移除；legacy `None` fallback 仍保留
     manual refresh，但它不是新資料入口主模型。
   - direct load compatibility service-success local refresh 已移除；Data Interpretation 仍是新資料入口
     product language。
   - Dataset sidebar channel-selection / clear-dataset service-success local refresh 已移除；mock /
     legacy fallback 仍手動刷新。
   - Dataset inline subject/session metadata edit service-success local refresh 已移除；mock /
     legacy fallback 仍手動刷新。
   - Preprocess sidebar filter / resample / rereference / normalize / epoch / reset service-success
     local refresh 已移除；mock / legacy fallback 仍手動刷新。
   - Visualization control sidebar montage / saliency service-success local refresh 已移除；mock /
     legacy saliency fallback 仍手動刷新。
   - `tests/architecture_compliance.py` 現在也會守住 post-command local refresh boundary：service-backed
     `execute_application_command()` 後不可直接呼叫 panel-local refresh method，除非該 path 明確是
     `refresh=False` query 或 failure / legacy fallback。
   - Missing-result legacy refresh branch 也已 guard：`result is None` branch 不可直接 local
     refresh，必須用 explicit legacy-result helper；`result.failed` branch 可保留 UI restore。
   - 保留的 mock / legacy shared-status fallback 也開始改走 coordinator helper；Preprocess
     epoch / reset compatibility path 現在會刷新 aggregate info 和 assistant backend status。
   - `MainWindow.switch_page()` 的 tab-switch refresh mapping 已移到
     `refresh_after_navigation()`；navigation refresh scope 也開始由 coordinator 定義。
   - `refresh_after_navigation()` 現在也有 same-main-window re-entrancy guard，與 command /
     observer refresh 的安全邊界一致。
   - 單純 observer `event -> update_panel()` bridge 已改成
     `BasePanel.refresh_from_observer()` -> `refresh_panel()`；需要特殊語意的 callback handler
     仍保留在各 panel。
   - Simple observer refresh call sites 已再收斂成 `BasePanel._create_refresh_bridge()`，避免
     各 panel 重複拼 `_create_bridge(..., refresh_from_observer)`。
   - `data_changed` / `preprocess_changed` observer events 現在使用 coordinator changed-state scope；
     DatasetPanel / PreprocessPanel owner bridge 一次刷新 downstream panels，其他同事件 subscriber
     不重複刷新。
   - MainWindow product runtime 的 aggregate info refresh 現在也不再由 InfoPanelService 直接
     訂閱 controller observer；MainWindow 建立 service 時關閉 direct observer bridges，shared
     status refresh 由 coordinator 呼叫 `MainWindow.update_info_panel()`。mock / legacy
     InfoPanelService context 仍可直接觀察 controller events。
   - InfoPanelService 的 direct `Study.get_controller(...)` bridge / list fallback 也已收進
     `get_legacy_controller_from_study()`；real `Study` aggregate info refresh 只走 state query /
     coordinator `notify_all()`，mock / legacy context 才可使用 controller bridge compatibility。
   - UI direct backend service execute guard 已補上：除 `application_capabilities.py` 的 shared
     helper 外，UI 不可直接 `BackendFacade(...).service.execute()`；InfoPanelService aggregate
     query 已改走 `execute_application_command(..., refresh=False)`。
   - training lifecycle observer events 也交由 TrainingPanel owner callbacks 觸發 centralized
     Training / Evaluation / Visualization refresh scope；Evaluation / Visualization 同事件 subscriber
     不重複刷新。
   - Downstream analysis refresh scope 已補進 coordinator：training / epoch / evaluation state
     changes 會刷新 Evaluation / Visualization readiness，而不是只等 controller observer 補刷新。
   - TrainingPanel 的 high-level `training_started` / `training_stopped` / `config_changed` /
     `history_cleared` callback 現在也會刷新 aggregate info panel 和 assistant backend status；
     high-frequency `training_updated` 仍維持自己的 live update loop。
   - `tests/architecture_compliance.py` 現在會阻擋新增
     `_create_bridge(..., self.update_panel)` 或 direct
     `_create_bridge(..., self.refresh_from_observer)`，防止 observer refresh boundary 回退。
   - dataset / preprocess / training / evaluation / visualization / assistant status 的 refresh scope
     要明確，避免每個 action handler 自己猜。
   - product runtime service-success path 不 silent fallback 到 controller mutation；mock /
     unit-test fallback 與 isolated legacy adapter 明確分離。
   - focused tests 覆蓋 `CommandResult.changed_state -> expected panel refresh / capability refresh`。
   - 文件明確標註 controller 長期是 adapter / read-only rendering / legacy compatibility，不是
     product workflow truth。
   - 這個 milestone 是 architecture cleanup follow-up；current local eval / validation closure
     可繼續，但完成品 claim 必須等它和 remaining human desktop acceptance 都關閉。

4. **把 Data Interpretation 從 Baseline Wizard 硬化成 Mature Import Wizard**
   - 補 embedded label editor、raw trigger selector、anchor reconciliation 和更清楚的
     blocked / needs-confirmation UX。
   - 對 BIDS、GDF external labels、MAT / CSV / TSV labels、EEGLAB、BrainVision、EDF annotations、
     XDF / LSL、自建資料 fallback 建立更完整的 user-facing capability boundary。
   - 所有 recipe reload 都要重新 preview / validate，且 UI 明確顯示差異。

5. **完成 UI Product Walkthrough**
   - consolidated automated human-like replay 已覆蓋 import -> preprocess -> epoch -> dataset ->
     training readiness -> evaluation / visualization / saliency readiness。
   - button-driven full train -> evaluate -> visualization / saliency render 還需要後續 polish /
     validation。
   - ChatPanel assistant-driven workflow 要能以使用者語言完成代表性流程，不暴露 raw tool
     syntax、schema 或 traceback。
   - Windows Desktop click-through、main window geometry、多螢幕與 loading 狀態需要真驗收。

6. **硬化 Agent Autonomy / Recovery**
   - 繼續讓 Context Assembler 只暴露 backend policy 允許或需要確認的 command。
   - 每一步都經 Verification Layer、capability policy、autonomy decision，並一次只執行一個
     verified command。
   - missing input、blocked、needs confirmation 和 recovery 要能在 UI 裡用人話回覆。

7. **完成 Automation Adapters / MCP 驗收**
   - 保留 CLI / headless runner 作為 CI、eval、batch 和 artifact 入口。
   - MCP Inspector GUI click-through 已有 screenshot / visible text / connected tools evidence；
     local HTTP transport / train job status-cancel 已有 stdlib client walkthrough artifact；same-session
     duplicate train start 也會被 resource guard 擋下。後續要補 evaluation / visualization jobs、
     job persistence / recovery 和更完整 client certification。
   - MCP tools 繼續使用同一套 Data Interpretation / command taxonomy，不直接操作 controller。
   - MCP client 不需要下載 XBrainLab 的大型科學計算與 UI 依賴；依賴留在 XBrainLab prepared runtime。

8. **把 Tool-call Benchmark 轉成 Thesis Report Evidence**
   - 目前 formal deterministic、local primary x3 和 local fallback x3 都是同一 `121 / 121`
     suite。最新 fast changed-case slice 已把 source suite 增至 `122` cases，新增中文
     label-action missing-input clarification；它只支撐 changed-case `1 / 1` gate，不更新正式
     thesis score claim。
   - Eval gate 要分層使用：fast dev gate 跑 deterministic changed / failed cases、repeat `1`、
     不跑 fallback；candidate gate 跑 primary affected families、repeat `1` 或 `2`、不跑 fallback；
     只有 release / thesis evidence 才跑 full primary / fallback x3。
   - Full local gate 前必須做 disk / cache / VRAM preflight；fallback x3 已觀察到 RTX 5070 Ti
     16GB 高壓 resource boundary，resource artifact 已保存。
   - Full-suite repeat `3` local runner 必須顯式帶 `--eval-gate release` 或
     `--eval-gate thesis`；預設 candidate gate 不會啟動 full local model run。
   - Deterministic CLI 預設 fast gate 也必須指定 changed / affected subset（`--case-id`、
     `--case-family` 或 `--case-limit`）；full-suite deterministic dashboard refresh 必須顯式
     帶 `--eval-gate release` 或 `--eval-gate thesis`。
   - Routine verifier、normalizer、prompt、case wording、UI refresh 或 backend cleanup slice 不應
     預設重跑 fallback x3；若 `nvidia-smi` 顯示 VRAM 接近滿載，full local release gate 應延後或
     明確記錄 blocked preflight。
   - 下一步要整理 score breakdown、failure taxonomy、case coverage 和重跑 protocol，避免只用
     pass rate 當報告。
   - benchmark 不能取代 UI / launcher / MCP / import wizard evidence。

9. **完成 Product Walkthrough And Release Gate**
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
