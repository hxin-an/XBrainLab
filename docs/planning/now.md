# XBrainLab Now

最後更新：2026-08-17

## 目前焦點

**在 `feat/assistant-no-model-tool-walkthrough-v1` 建立不載入 Granite 的真人前端 tool walkthrough，
並讓 normal `switch_panel` 只有在目標 UI 真正 ready／failed 後才產生 terminal。**

使用者已於 2026-08-17 明確同意：`--tool-debug` 自動打開 Assistant、使用 debug-only compact
status strip，以及修改 normal `switch_panel` 的可見 async completion／failure 行為。本 slice 會交付
給使用者手測，取得批准前不合入 `main`。Repo-root `settings.json` 仍是使用者本機 runtime設定，
不得 stage、revert或隱藏。

## 問題與證據

- 現有 `--tool-debug` 雖由 Enter 依序取 scripted call，開啟 Assistant 時仍會走 first-run與
  `AssistantRuntimeLifecycle.activate()`；runtime／controller 未 ready 時 case已先被消耗，因而不能
  作為真正的 no-model frontend smoke。
- Current JSON的 `expected` 未被Qt流程消費，`confirmed=true` 又會跳過真實 confirmation card；
  async handoff、panel materialization或training尚未terminal時，下一次Enter可能和前一步競態。
- Normal `switch_panel` 在 typed request發出後就顯示「Opened」語意，沒有等待
  `MainWindow.switch_page(... on_ready/on_failed)`；lazy materialization失敗時Assistant也收不到
  correlated terminal，重複／stale callback可能覆寫較新的navigation。
- Phase A 的24-case／21-action headless showcase已於PR #31合入；它驗證backend boundary，但不開Qt、
  不載入模型、不證明真人按鈕／dialog／panel狀態。

## Observable outcome

- `python run.py --tool-debug <profile.json>` 在沒有local model cache時直接進入debug session並自動打開
  Assistant，不進行model selection、download、Granite初始化或prompt inference。
- Debug-only compact status清楚顯示step、action、expected completion與等待原因。Enter只有在前一步
  terminal後才消耗下一步；confirmation、workflow UI handoff、panel materialization與training期間
  不能跳步。實際Confirm／Cancel沿用現有UI，profile不得以`confirmed=true`繞過。
- Canonical `xbrainlab.tool_walkthrough.v1` profile精確涵蓋21 actions；使用session temp synthetic FIF，
  training固定real CPU EEGNet、1 epoch、batch 2、learning rate 0.001。另有navigation profile覆蓋5個
  panels、4個Visualization subviews、repeat與invalid requests。
- Normal `switch_panel` 保留現有MainWindow ownership，但Assistant terminal必須對同一request等待
  `on_ready`或`on_failed`；stale／duplicate completion忽略，失敗可見且可retry。

## Scope、ownership與complexity

- Owner before／after：ApplicationService仍擁有command/capability；既有confirmation owner不變；
  MainWindow仍擁有panel materialization；AssistantRuntimeLifecycle仍擁有normal model runtime。
  Debug walkthrough只是同一tool/command/UI boundary的host，不新增產品workflow owner。
- Deletion／reuse first：重用`ToolDebugMode`、`ToolExecutor`、ApplicationToolRuntime、既有chat
  presentation、confirmation card與panel callbacks；不複製21-tool catalog、command state或UI表單。
- 此new feature預算production net LOC不超過600、production files不超過10、owner增加0；同一PR分成
  walkthrough與switch-panel兩個implementation commits。超過預算或需要新owner時先拆PR。
- Non-goals：不評估Granite selection accuracy、不下載model、不做scientific quality claim、不建立
  persistent pass receipt、不讓debug mode成為production user feature、不修其他Assistant架構問題。

## Ordered implementation

1. Characterize現有debug consume-before-terminal、runtime activation與switch-panel early-success；先加
   能抓到真退化的focused red tests。
2. 將debug session與normal runtime activation分流：auto-open Assistant，建立model-free executor／
   existing UI adapters，新增versioned profile parser與compact status；只有correlated terminal可advance。
3. 加入21-action與navigation profiles；所有需要confirmation／UI review／training的step明確pause，
   使用者完成既有UI後才繼續。
4. 讓normal switch-panel navigation帶request identity，從MainWindow ready／failed callback回到既有
   presentation／command lifecycle；latest request wins，失敗顯示recoverable response。
5. 跑focused unit/integration、no-model subprocess、Qt offscreen screenshot/walkthrough、Ruff、
   Basedpyright與applicable validation。交付exact SHA與manual steps；使用者批准前不merge。

## Focused validation與stop conditions

- Cold/missing model cache下`--tool-debug`不得import／initialize Granite或觸發download；21 actions exact
  cover canonical catalog，profile未知欄位／terminal／`confirmed=true` fail closed。
- Double Enter、busy、confirmation、UI handoff、training與panel lazy load都不得消耗下一step；failure
  保留目前step並允許retry或明確skip/cancel，不可silent advance。
- `switch_panel`測試必須用delayed ready、failure、out-of-order與duplicate callback，驗證terminal時機、
  visible response及latest-wins；只測UiRequest emission不算完成。
- Screenshot／walkthrough檢查debug status在default與窄視窗的fit、contrast、hierarchy與disabled state；
  offscreen artifact不取代使用者native手測。
- 若需要第二套ApplicationService state／confirmation policy、owner增加、production超過600 net LOC／
  10 files，或無法在不載模型時走同一execution boundary，停止並拆分或重新確認。

## Implementation checkpoint

- Branch由PR #31 merge commit `eb007163`建立。Implementation已以`594957a8`提交並在draft PR #32
  追蹤；使用者既有`settings.json`仍dirty且不在本slice。
- Debug session現在以diagnostic runtime綁定既有controller／dispatcher但不呼叫model initialize；v1
  walkthrough透過既有ToolAttemptCoordinator、confirmation card、ApplicationService與UI handoff執行，
  terminal前不consume step。Normal `switch_panel`由MainWindow ready／failed callback回傳同一request
  identity，stale／duplicate resolution不會完成turn。
- Canonical profiles位於`scripts/dev/agent_tool_walkthrough/`：21-action profile與model-facing catalog exact
  相等，session temp FIF為4 channels、left/right events；navigation profile覆蓋5 panels、4 subviews、repeat
  與invalid requests。
- Complexity checkpoint：9個production files、production net +599 LOC、owner +0，未超過批准上限。
- Focused unit／integration、Ruff、Ruff format與Basedpyright已通過。真實offscreen Qt diagnostic各執行
  `switch_panel`與`list_files`一個terminal，metrics皆為`llm_calls=0`、`tools=1/1`；截圖在
  `build/dev-artifacts/agent-tool-walkthrough/`。這些只證明Linux offscreen wiring，不取代native手測。
- PR #32 CI揭露兩個既有capture controller doubles未實作新增的typed panel-resolution contract，
  dispatcher因此正確fail closed；另有一個debug integration test在未show widget時誤驗`isVisible()`。
  修正只補capture doubles與真實顯示test setup，不放寬production dispatcher或修改產品UI；對應contract、
  完整human-like Qt capture、ChatPanel UI UX capture與debug integration gates均已通過。
- 下一步：推送capture contract修正並等待PR #32同一head的non-skipped CI全綠，再交付exact head SHA。
  使用者依README先跑navigation profile、再跑21-action profile；只有同一SHA手測通過並明確批准後才可merge。
