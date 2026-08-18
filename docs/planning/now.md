# XBrainLab Now

最後更新：`2026-08-18`

## 目前焦點

在 `refactor/assistant-target-adapters-v2` 完成 Assistant 真人走查候選，修復 action routing、
Compute Saliency completion 與 `respond_to_user` 可見行為，再物理刪除舊 response-action UI。
本輪完成前不測 Granite selection、不合併 integration 或 main。

目前 phase：`Active；implementation complete，candidate validation`

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

## Focused validation 與人工 stop boundary

- Registry仍精確18 tools，`respond_to_user`只能走reserved response path；message空值／額外key fail closed。
- Response使用current backend stage、正常MESSAGE presentation與completed terminal；ToolExecutor、
  confirmation、navigation及Application mutation皆為零次，第二步Dataset navigation仍可執行。
- Direct navigation驗證順序為admission／confirmation → navigation request → execute；blocked零導航。
- Saliency驗證confirmation → action handoff → panel busy → exact operation terminal；stale、duplicate、
  cancel、blocked與failed皆釋放turn且不誤報completed。
- Source guard與Qt assertions證明response-action UI／payload已不存在、empty-state prompts仍存在，
  long-running card只有核准欄位；可見變更另產生320／420／760px artifacts。
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
