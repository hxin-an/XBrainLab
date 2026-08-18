# XBrainLab Now

最後更新：`2026-08-19`

## 目前焦點

在 `refactor/assistant-target-adapters-v2` 完成 Assistant 真人走查候選，修復 action routing、
Compute Saliency completion 與 `respond_to_user` 可見行為，再物理刪除舊 response-action UI。
本輪完成前不測 Granite selection、不合併 integration 或 main。

目前 phase：`Active；candidate validation`

## 問題與證據

- Approved target 是 18 個 Application tools，加上一個保留的 `respond_to_user` response branch；
  response 不是第 19 個 tool，也不得進 ToolExecutor。目前 no-model walkthrough 只接受 18 個
  registry names，因此沒有真人證據證明 strict response 能進正常 Assistant bubble、結束 turn 並
  讓下一步繼續。
- 五個 direct preprocessing actions 已有真 ApplicationService side effect，但成功前不會開啟
  Preprocess panel；`select_channels` 則應維持 Dataset panel。前置條件 blocked 時不應切頁。
- Exact runtime log 已證明 confirmed `compute_saliency` 發出 action handoff 後，被
  AgentManager 以「outside its active turn」拒絕。Controller 對 action route 正確發布
  `RUNNING_COMMAND`／無 decision owner，但 Host identity guard 只接受 dialog/panel 的
  `WAITING_FOR_DECISION`，所以既有 VisualizationPanel Compute 沒收到請求、按鈕不會進 Computing。
- Failure path 目前仍可附帶舊 `Suggested next step` buttons。這個 response-action subsystem 是
  過去殘留的第二互動面，不是本輪新需求；使用者已要求完整刪除，保留 empty-state 靜態 prompt cards。
- Long-running confirmation 仍以 generic `Long-running action`、Reason 與 Action details 呈現；
  使用者已核准收斂成產品 action 名稱、Impact、Confirm／Cancel。

- 真人 `response-presentation` 手測發現一般藍色 Assistant 回答的文字視覺上偏：外層
  bubble 上下 margin 各 10 px，但 prose view 預留的 8 px 防裁切高度全落在文字下方。
  使用者已明確核准只修正一般藍色回答的垂直置中；水平位置、文字左對齊及
  success／attention／error／cancelled／user bubbles 不變。

## Observable outcome

1. `respond_to_user` diagnostic 由當下 ApplicationService publication 取得 workflow stage，組成
   strict三欄 envelope，經既有 `CommandParser` 與正常 response finalization 顯示藍灰 Assistant
   bubble；不註冊成 tool、不執行、不確認、不導航、不 mutation。完成後下一個 Enter 可正常 dispatch。
2. Direct tools 只在通過 admission／confirmation 後、ApplicationService execute 前做 companion
   navigation：五個 preprocess與reset開 Preprocess，training lifecycle開 Training；blocked 不切頁。
   GUI handoff保持既有 owner，`select_channels`固定 Dataset，`switch_panel`仍是模型唯一純導航 tool。
3. Confirmed Compute Saliency action 使用 exact turn/request/tool identity，允許 action route 的
   `RUNNING_COMMAND`狀態，呼叫既有 VisualizationPanel Compute，顯示 Computing，並等待同一
   operation 的 completed／cancelled／blocked／failed terminal。不得新增 backend command或運算 owner。
4. `Suggested next step` response-action types、payload、renderer、buttons與dispatch全部移除；failure
   只保留 typed bubble。Empty-state suggestion prompts不變。
5. Long-running card只顯示產品 action名稱、Impact與Confirm／Cancel；setting-change與destructive
   confirmation的既有詳細資訊不變。
6. 一般藍色 Assistant 回答的 prose 內容在保留既有 8 px 防裁切高度、bubble
   總高與寬度 contract 的前提下上下視覺置中；不改其他 presentation kinds。

## Scope、complexity 與修理順序

使用者已明確核准上述可見文案、導航、確認卡與刪除。Non-goals：不改ApplicationService capability、
preprocess semantics、Granite generation／prompt、model cache、panel layout、theme、tool membership、
backend saliency lifecycle或root `settings.json`。

Owners before／after皆為既有ApplicationService、Controller、WorkflowUiHandoffHost、MainWindow／
VisualizationPanel與ChatPanel；不新增owner、state machine、receipt、module、public class或compatibility
path。Slice A預估3–5個production files、約`+50/-20`；Slice B1最多8個production files且為淨刪除；
Slice B2只精簡既有confirmation card。若任一slice超過8個production files、bug fix淨增300 LOC、pure refactor淨增100 LOC，
或需要新owner，立即停止並重新拆分。

依序執行：

1. Red tests：response walkthrough目前不接受保留branch；direct command不導航；confirmed saliency
   action handoff被active-turn guard拒絕。
2. Slice A：加入model-free response replay、direct companion navigation、route-aware saliency
   identity guard與`response-presentation.json`；保持18-tool registry不變。
3. 跑同一focused tests與直接相鄰controller／AgentManager／Visualization／no-model integration。
4. Characterization：鎖定現有response-action call sites與long-running card；確認empty-state prompts
   是獨立surface。
5. Slice B1：物理刪除response-action subsystem；不隱藏殘留、不建立replacement。
6. Slice B2：精簡long-running confirmation card。獨立施工以避免B1同時觸及超過8個production files。
7. 跑focused UI／history／controller tests、Ruff、Basedpyright、MkDocs及exact-source visual capture，
   固定candidate commit後交付真人walkthrough。

Checkpoint（2026-08-18）：Slice A、B1、B2皆完成。reserved response replay、9個direct companion
navigation、route-aware saliency handoff與response walkthrough已實作；response-action types、history
payload、renderer、buttons與dispatch已物理刪除；long-running card已收斂成產品action、Impact與
 Confirm／Cancel。Ruff與865個focused/adjacent cases中的舊response-action預期已完成遷移，失敗項
 逐項回歸為green；下一步只執行candidate validation、visual capture與真人walkthrough handoff。

Handoff blocker（2026-08-19）：真人首次啟動在Assistant UI construction時以
`Assistant walkthrough profile was not found`失敗。CLI目前將`--tool-debug`相對路徑原樣保存到
QApplication，而ChatPanel延後建立才讀檔；啟動工作目錄與repo root不同時就會失效。修復只限
`run.py`啟動seam：先以呼叫端目錄解析，若不存在再以repo root解析，驗證為regular JSON file後保存
absolute path；不存在時由argparse在Qt UI建立前清楚拒絕。Red protection必須模擬解析後working
directory改變仍可由ChatPanel載入；不改ToolDebugMode schema、正常模型路徑或產品UI。

Checkpoint（2026-08-19）：上述launcher seam已完成red→green。Repo-relative內建profile在非repo
working directory解析後仍能由`ToolDebugMode`載入；Ruff、Basedpyright與151個launcher／profile／
debug integration／ChatPanel相鄰測試通過。`eabe7959`的真人批准尚未發生且已由本修正取代；固定新的
local candidate commit後重新執行受影響的首次啟動手測。

UI repair（2026-08-19）：先以一行藍色 Assistant prose 建立上下可見留白的紅測試，
再只重新分配該 presentation 的 prose viewport 垂直 guard。英文、中文與換行在
320／420／760 px 及 100／125／150% scale 的上下差距不得超過 1 logical px；現有
`documentSize + 8`、wrapping與clipping assertions不得放寬。完成focused tests、Ruff、Basedpyright與
exact-source response screenshot後，回到真人 `response-presentation` 驗收；本次source修改會使先前手測失效。

Checkpoint（2026-08-19）：上述 UI repair 已完成 red→green。藍色 Assistant prose 在三種寬度、
英文／中文／換行與100／125／150% offscreen scale的上下差距為可接受範圍；其他
presentation kinds不套用新inset。201個MessageBubble／ChatPanel／capture-contract相鄰測試、
Ruff、Basedpyright、format check、focused ChatPanel walkthrough與7張default baseline comparison均通過。
上述仍只是Linux／Qt offscreen checkpoint；下一步是在固定candidate source重跑真人
`response-presentation`。

真人 `complete-workflow` 新發現（2026-08-19）：panel navigation completion仍使用
`Opened the … panel in XBrainLab.`；raw normalization completion以queued／per-EEG-epoch描述正確的
deferred語意但不易讀；Select Model completion丟棄UI已知的實際model名稱；一般confirmation仍顯示
generic `Confirmation required`與比內文小的`Reason`標籤。使用者已核准以下最小呈現修復：panel改為
`Opened Training panel.`同型句法、Visualization subview改為`Opened Saliency Map in Visualization
panel.`同型句法；deferred normalization改為`Z-score normalization will be applied independently to
each EEG epoch when epochs are created.`同型句法；Select Model顯示`Model selected: EEGNet.`同型結果；
一般confirmation以實際action作標題，移除generic title、重複action描述與`Reason`標籤，原因內文直接
置於標題下。Long-running、setting-change與destructive card保持既有專屬結構。

這個修復只改既有Controller／ApplicationService result copy、TrainingSidebar completion detail與
AssistantConfirmationCard presentation；不改tool membership、ApplicationService command/capability、
normalization計算、saliency operation lifecycle或任何owner。Owners before／after不變；預估5個
production files、淨行數接近零，刪除候選是一般card的generic title與重複label branch。先以精確可見
結果建立red tests，再做最小修復。`compute_saliency`本身維持只在`TRAINED`發布；另以passing
characterization明確鎖定`is_training=True`即使`finished_run_count>0`仍優先為`TRAINING`，並重跑
backend active-training拒絕與Visualization按鈕隱藏證據。完成focused unit／Qt tests、320／420／760px
visual artifacts、Ruff、format check與Basedpyright後，固定新candidate並重新執行受影響的
`complete-workflow`；任何source再改仍使該手測批准失效。

Checkpoint（2026-08-19）：上述呈現修復已完成。14個舊copy／card assertions先以預期原因失敗，
實作後連同3個saliency stage／capability cases共17個focused cases通過；直接相鄰的Controller、
preprocess service、response presentation、pipeline stage、ChatPanel、confirmation card、TrainingSidebar、
capture contract與no-model debug integration共609 tests通過。Production實際5 files、`+26/-13`、
net `+13`，owners不變且未觸發complexity threshold。Ruff、format check、Basedpyright與diff check通過；
`build/dev-artifacts/chatpanel-ui-ux-ordinary-confirmation/`的320／420／760px ordinary confirmation
artifacts由主agent檢視，均顯示action-first title、直接原因內文與未溢出的Cancel／Compute按鈕，artifact
gate status為passed。這些仍是Linux／Qt offscreen checkpoint；下一步只交付新的exact-source真人
walkthrough，不宣稱Windows native acceptance或handoff-ready。

真人後續呈現調整（2026-08-19）：使用者要求bandpass／notch成功訊息移除括號，統一為
`Applied bandpass filter: 1.0-40.0 Hz.`與`Applied notch filter: 60.0 Hz.`同型句法；confirmation
card只移除可見的`Impact`小標，以降低視覺噪音，原本的impact說明內文完整保留。這只改result copy與
card renderer；typed risk、confirmation admission、correlation、說明內文、按鈕與執行policy全部
保留。Impact title widget直接刪除而不是只設為hidden；capture payload仍保留impact內文證據。先建立
copy與widget-absence紅測，再跑相同focused／adjacent tests、重產320／420／760 artifacts與靜態檢查；
任何source變更仍使舊真人批准失效。

Checkpoint（2026-08-19）：這個小幅呈現調整已完成。精確copy與widget-absence紅測先得到6 failed／
3 passed，實作後9個focused cases通過；直接相鄰的preprocess、mock tool、confirmation card、ChatPanel
與capture contract共223 tests通過。Ruff、format check、Basedpyright與diff check皆通過；搜尋確認產品
與文件已無舊括號句法，`impact_title`只剩測試中的absence assertion。重新產生的
`build/dev-artifacts/chatpanel-ui-ux-no-impact-label/` gate為passed，主agent檢視320／420／760px artifacts：
Impact小標已消失，原本說明內文、action標題與Cancel／Confirm按鈕皆完整可見且未裁切。Owners不變，
沒有新增state、policy或owner；這仍是Linux／Qt offscreen checkpoint，必須由使用者在新exact source
重新真人手測後才可作merge acceptance。

## Focused validation 與人工 stop boundary

- Registry仍精確18 tools，`respond_to_user`只能走reserved response path；message空值／額外key fail closed。
- Response使用current backend stage、正常MESSAGE presentation與completed terminal；ToolExecutor、
  confirmation、navigation及Application mutation皆為零次，第二步Dataset navigation仍可執行。
- Direct navigation驗證順序為admission／confirmation → navigation request → execute；blocked零導航。
- Saliency驗證confirmation → action handoff → panel busy → exact operation terminal；stale、duplicate、
  cancel、blocked與failed皆釋放turn且不誤報completed。
- Source guard與Qt assertions證明response-action UI／payload已不存在、empty-state prompts仍存在，
  long-running card只有核准欄位；可見變更另產生320／420／760px artifacts。
- 藍色 Assistant prose 的上下留白差距最多 1 logical px；使用者、semantic status、Markdown、
  CJK、streaming、wrapping與code block高度不回歸。
- 同一candidate SHA依序真人執行 `response-presentation`、`contract-failures`、`gui-cancellation`、
  `complete-workflow`。任一步unexpected terminal、頁面錯誤、Suggested-next-step殘留、確認後卡住或
  Compute未進busy／terminal即停止；source再改使受影響手測失效。

Local focused evidence與真人手測通過後才push PR #39。PR base/head精確、所有applicable non-skipped
checks completed/success，且使用者明確記錄日期、範圍與source並同意merge後，才以merge commit合入
`integration/assistant-stable-v2`。真Granite的response/tool selection是下一個獨立slice；main仍等待
完整integration candidate。

## Stop conditions

- `respond_to_user`被加入tool registry、到達ToolExecutor，或workflow stage由script提供。
- Companion navigation變成新的readiness owner、blocked仍切頁，或GUI handoff的既有owner被替換。
- Compute建立第二套selection／operation lifecycle，或非exact operation terminal結束turn。
- Suggested-next-step只被隱藏而資料／dispatch仍殘留，或empty-state suggestions被誤刪。
- UI/source改動超出已核准行為、碰觸`settings.json`，或驗證需要放寬既有assertion才能通過。
