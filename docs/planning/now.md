# XBrainLab Now

最後更新：`2026-08-16`

## 目前焦點

**在 `assistant/toolbar-floating-polish-v1` 收斂 Assistant 標題列、Settings 停用列與 floating dock
互動，讓每個可見圖示直接執行自己的功能，且浮動視窗可以真的移動。**

## 問題與證據

- New chat 已有獨立按鈕，但目前使用 document icon；使用者要求改成明確的 `+`。
- Gear 仍是包含 Assistant settings、Float assistant、New chat 的選單按鈕；New chat 重複，gear 在右上角
  的視覺對齊也不自然。
- Float assistant 藏在 gear 選單，沒有獨立 direct action；浮動後 custom dock title bar 只把 mouse
  events 設為 ignored，現有測試也只驗 event flag，未證明 floating window geometry 真的會改變。使用者
  已實際觀察到浮動框不能移動。
- 寬標題列曾額外顯示 generic Retry，會讓操作數量依狀態變成五顆；使用者已決定移除 header Retry，
  保留 response/error flow 的 typed Retry action。
- Settings 的 Assistant group 只有一顆 `Disable Assistant…`，視覺上缺少和其他設定列一致的狀態標籤。
- PR #28 head `14b67ee497c2bf59b2ab41e345068c85164d6cac` 的使用者手測尚未通過：local
  runtime 載入途中開啟 Settings 並按 Delete，整個 UI 失去回應。Settings 只投影 download lifecycle，
  因此 runtime `LOADING` 時仍把已安裝 cache 顯示為可刪；既有 delete 測試又 mock 掉所有 message box，
  沒有覆蓋 active modal 上由 main window 再開 modal warning 的 nested-modal failure。
- 同一 head 點 Float 後整個 XBrainLab 立即失去回應，尚未進入拖曳。現有 click callback 同步呼叫
  `setFloating()`，在發出 click 的 custom titlebar 被 reparent 後又同步設定 dock geometry，形成 Qt native
  hierarchy transition 的高風險路徑。
- Settings 齒輪亮度正常，但 `settings.svg` 缺少右上齒輪路徑，且 stroke 直接貼住 viewBox 邊界，16 px
  raster 會被裁切；Float/Dock 則使用 platform theme icon，實際顯示太暗而像 disabled。
- PR #27 已以 `cf80db94fb3b2850f10e15078f2cca8e2b49751e` 合入 `main`；本 slice 從該產品基線開始，
  repo-root `settings.json` 仍是唯一受保護的本機 dirty path。

## Observable outcome

- Assistant header 固定為四個 30×30 direct controls，依序為 `+` New chat、Float/Dock、Assistant
  Settings、Hide。每顆都有明確 tooltip、accessible name/description、keyboard focus 和獨立 click action。
- Gear 直接開啟 Settings，不再有 menu；New chat、Float/Dock、generic header Retry 的重複 menu/action
  surfaces 全部刪除。
- Float/Dock 使用同一顆按鈕：docked 時顯示 Float assistant，floating 時切為 Dock assistant。浮動視窗
  可由 header 空白區移動；按鈕區不誤觸 drag，使用者移動後不會被自動放回初始位置。
- Settings 的 Assistant group 顯示 `Assistant is enabled` + `Disable`；停用中顯示 `Disabling…`，terminal
  success 後顯示 `Assistant is disabled` 且按鈕 disabled。既有 confirmation、cache 保留、conversation
  clear 與 runtime lifecycle 語意不變。
- Local runtime 正在載入 selected model 時，Settings 的 cache action 顯示 disabled `Loading…`；runtime
  已持有該模型時，Delete 只在 Settings 自己的 modal hierarchy 內提示先 Disable，不得刪除或凍結。
- 點 Float/Dock 的事件派送完成後才切換 hierarchy；轉換期間不能重複排程，整個 app event loop 必須持續
  回應。浮動位置交由 Qt/window manager 保留，不在 transition 內同步覆寫 geometry。
- Settings 齒輪保持既有亮度，只補齊對稱 geometry 與 raster padding；Float/Dock 使用 repo-owned、與
  Settings enabled 亮度一致的 icon，不再依賴過暗的 platform theme icon。
- 320 px dock floor、default-scale 與 Windows 100/125/150% DPI 下不得 clipping、overlap、突出或失去
  keyboard reachability。

## Scope、ownership 與 non-goals

- `AgentManager` 繼續擁有 dock/header presentation；`AssistantDockTitleBar` 只處理 title interactions；
  `ModelSettingsDialog` 只投影既有 config/lifecycle state。Owner before/after 不變。
- 優先刪除 `QMenu/QAction`、三個 menu actions、generic retry button/state 與重複 float placement；不新增
  dock owner、state machine、receipt、compatibility shim、icon package、public API 或 production module。
- 不改 Assistant runtime、tool calls、model/download、ChatPanel response semantics、EEG workflow、主視窗其他
  panel 或 `settings.json`。
- 預期最多三個 production UI files與三個 icon/resource files，production net LOC 仍低於 pure-refactor
  review threshold；不新增 owner、state machine、receipt、compatibility path、production module 或 public
  API。若必須取代 `QDockWidget`，先做 complexity review 並停止擴張。

## Ordered repair

1. 先新增能在目前 head 因 exact defect 失敗的 tests：runtime `LOADING` delete state、正確 modal parent與
   confirmation race；Float 必須延後 hierarchy transition、維持 Qt heartbeat 且不同步定位；icon raster
   必須抓到齒輪右上缺角、邊界裁切與 Float 過暗。
2. 讓 Settings dialog 訂閱既有 runtime snapshot；LOADING 時停用 cache action。將 model deletion admission
   收斂為無 UI 副作用的 bool check，confirmation 前後皆 recheck，所有 warning 由 Settings dialog parent。
3. Float/Dock 透過下一個 event-loop tick 執行 `setFloating()`，以 view-local pending flag 防止重疊切換；
   刪除 transition 內的 screen placement、dock geometry與 dock minimum-size mutation，內容 floor 留在
   ChatPanel。`startSystemMove()` 改在 mouse press 啟動，只有 platform拒絕時才走 pointer-delta fallback。
4. 補齊 Settings 齒輪 path 並增加 viewBox padding，不改其顏色；新增 repo-owned Float/Dock icons，沿用
   Settings 的 enabled stroke brightness。`+`、Settings 與 Close 的既有顏色／動作不變。
5. 重跑 identical focused tests、直接相關 integration、Ruff、Basedpyright、MkDocs strict；產生並人工查看
   runtime-loading Settings、320 px header、floating/docked default-scale candidates。Windows DPI gate仍由
   PR 的 required CI 執行，offscreen heartbeat不冒充 native WSLg acceptance。
6. Push exact source並重新等待 PR #28所有 applicable CI。使用者需在新 exact head重測 loading delete、
   gear、Float responsiveness、drag/dock後，另行明確同意 merge。

## Implementation checkpoint（2026-08-16）

- 舊 focused baseline 12 tests 通過；新增 exact loading-delete、modal parent/race、deferred Float、geometry
  deletion、press-time system move與 icon raster contracts後，現況依預期為9 failures／11 passes，實作後
  同一範圍20／20通過。
- Settings 現在投影既有 runtime snapshot：selected model LOADING時顯示disabled `Loading…`；READY但仍
  in-use時，所有 warning由Settings dialog parent。Admission在confirmation前後各檢查一次，AgentManager
  不再建立第二個main-window modal。
- Float/Dock在下一個event-loop tick才切換，pending期間不接受重複click；同步screen placement、dock
  geometry與dock minimum-size mutation已刪除。真實QDockWidget float→dock heartbeat、press-time native
  system move與pointer-delta fallback皆有測試。
- Settings齒輪補齊缺失右上路徑並增加raster padding，顏色未改；Float/Dock改用同亮度repo-owned SVG。
  完整walkthrough PASS，主agent已查看320 px header、READY及runtime-loading Settings候選。
- 直接相關完整sweep為242 unit tests、17 product/toolbar/polish tests與28 capture/baseline contract tests；
  Ruff check/format、Basedpyright與MkDocs strict通過。更新唯一受影響的`ai-assistant-open.png` reference後，
  7張default-scale artifacts全部匹配（max mean diff 0.305、max changed 0.90%）。
- Production為六個既有UI/resource surfaces，147 additions／76 deletions、net `+71` LOC；沒有新增production
  module、public class、owner、state machine、receipt或compatibility path。受保護的`settings.json`未納入。
- PR #28仍是checkpoint：需commit/push新exact source、等待全部required CI success，再由使用者重測三項
  blocker並明確同意merge；舊head `14b67ee497c2bf59b2ab41e345068c85164d6cac` 的批准全部失效。

## Stop conditions

- 若 Qt system move 與 manual fallback 都不能在真實 WSL/native window 移動 floating dock，停在 checkpoint，
  不以 offscreen event flag 冒充成功。
- 若延後 `setFloating()` 並刪除同步 geometry mutation 後，native WSLg 點 Float 仍讓整個 app event loop
  凍結，PR 保持 checkpoint；不自行建立第二套 floating window owner。
- 若 visual candidate 未由主 agent 實際查看、approved reference 不匹配、任何 required CI 非 success，或
  exact-source manual acceptance 尚未取得，不稱 handoff-ready、不合入 `main`。

長期目標讀 [Roadmap](roadmap.md)，evidence contract 只讀 [Validation](../validation/README.md)。
