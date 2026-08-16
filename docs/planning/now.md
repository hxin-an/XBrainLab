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
- 320 px dock floor、default-scale 與 Windows 100/125/150% DPI 下不得 clipping、overlap、突出或失去
  keyboard reachability。

## Scope、ownership 與 non-goals

- `AgentManager` 繼續擁有 dock/header presentation；`AssistantDockTitleBar` 只處理 title interactions；
  `ModelSettingsDialog` 只投影既有 config/lifecycle state。Owner before/after 不變。
- 優先刪除 `QMenu/QAction`、三個 menu actions、generic retry button/state 與重複 float placement；不新增
  dock owner、state machine、receipt、compatibility shim、icon package、public API 或 production module。
- 不改 Assistant runtime、tool calls、model/download、ChatPanel response semantics、EEG workflow、主視窗其他
  panel 或 `settings.json`。
- 預期最多三個 production UI files，production net LOC 接近持平或下降。若超過 +100 net production LOC、
  三個 production files，或必須取代 `QDockWidget`，先做 complexity review 並停止擴張。

## Ordered repair

1. 以現有 15 個 toolbar/Settings focused tests 為 green characterization baseline；先新增會因 exact four-icon
   contract、direct actions、real geometry movement 與 settings status row 而失敗的 red tests。
2. 在既有 header/dock owner 中刪除 menu/retry surfaces，建立四顆 direct controls；Float 優先使用 Qt
   system move，平台拒絕時才用 pointer delta fallback，且只在 float transition 定位一次。
3. 將 Settings Assistant group 改為狀態標籤 + compact Disable action；不改 lifecycle contract。
4. 更新直接耦合的 product walkthrough/recovery caller，改為實際 click `float_btn`，不保留舊 QAction
   compatibility path。
5. 重跑 identical focused tests、直接相關 integration、Ruff、Basedpyright、MkDocs strict；產生並人工查看
   default-scale candidate。只有 candidate 超出既有 approved threshold 時才更新受影響的 Assistant
   reference；Windows DPI gate 仍由 PR 的既有 required CI 執行。
6. Push exact source、開 PR 並等待所有 applicable CI。使用者需在 exact head 手測四個 direct actions、
   floating drag/dock 與 Settings 狀態列後，另行明確同意 merge。

## Implementation checkpoint（2026-08-16）

- Characterization baseline 先以 15 tests 通過；新增的 exact toolbar、direct click、floating geometry 與
  Settings state-row tests 依預期出現 8 個 red failures，實作後相同測試全部轉綠。
- Header 現在只有固定的 `+`、Float/Dock、Settings、Hide 四顆 direct buttons。舊 `QMenu/QAction`、重複
  New chat/Float actions 與 generic header Retry state 已刪除；response/error 的 typed Retry 不變。
- Floating title drag 優先交給 Qt window-system move；平台不接受時由同一 title bar 依 pointer delta 移動
  dock。測試會驗證 floating geometry 實際改變，不再只看 event accepted/ignored flag。
- Settings Assistant group 已呈現 enabled/disabled state 與 compact `Disable`，並沿用既有 async lifecycle、
  confirmation、cache 與 conversation semantics。
- 五次直接相關 focused runs 分別通過 71 toolbar/Settings/recovery、173 AgentManager、32 product/capture、
  23 recovery runtime 與 16 baseline/DPI contract tests；Ruff check/format、Basedpyright、MkDocs strict 皆通過。
  Default-scale 7 張圖與 approved references 通過（max mean diff 0.875、changed pixels 1.99%），因此沒有
  為了本 slice 改寫 reference；完整 UI walkthrough 也通過，主 agent 已實際查看 320 px header 與 Advanced
  Settings 截圖。
- Production 只改兩個既有 UI files，合計 111 additions／130 deletions，net `-19` LOC；沒有新增 module、
  public class、owner、state machine、receipt 或 compatibility path。受保護的 `settings.json` 未納入變更。
- 剩餘工作是 commit/push、PR required CI 與 exact-source 手測。Offscreen geometry test 不冒充 Windows
  native floating-window 手感；未取得使用者手測通過與 merge 同意前不合入 `main`。

## Stop conditions

- 若 Qt system move 與 manual fallback 都不能在真實 WSL/native window 移動 floating dock，停在 checkpoint，
  不以 offscreen event flag 冒充成功。
- 若 visual candidate 未由主 agent 實際查看、approved reference 不匹配、任何 required CI 非 success，或
  exact-source manual acceptance 尚未取得，不稱 handoff-ready、不合入 `main`。

長期目標讀 [Roadmap](roadmap.md)，evidence contract 只讀 [Validation](../validation/README.md)。
