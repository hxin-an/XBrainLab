# XBrainLab Now

最後更新：`2026-08-16`

## 目前焦點

**在 `assistant/toolbar-floating-polish-v1` 修復 PR #28 exact head `202a7b53` 手測暴露的
Assistant model install terminal、Settings confirmation 與 WSLg floating freeze；四項全部在新
exact source 手測通過前不合併。**

使用者已於 `2026-08-16` 明確授權實作本輪 UI 行為與必要的 backend lifecycle 修正，並選擇：

- model deletion success 改為行內 `Not installed / Install Model`，不再彈 blocking success dialog；
- 若 `QDockWidget.setFloating()` 在 WSLg/xcb 仍是原生阻塞點，改用 AgentManager-owned 獨立浮動視窗，
  不停用目前主要環境的 Float。

## 問題與證據

- **Install terminal blocker**：本次冷安裝約 `22:11` 開始，UI 到 99% 後直到 `22:21` 關閉都沒有
  success、failure 或 cancel terminal。現有進度不是 Hugging Face 真實總量，而是每 0.5 秒用 model
  cache bytes 除以固定 `5.08 GB` 估算並封頂 99%；現有 unit test 也只鎖定 99 可被發出，沒有鎖定其後
  必須 terminal。Xet log 顯示 HTTP 416、最長約 315 秒 reconstruction，最後停止活動；app 關閉後
  pinned snapshot 已被現有 product validator 判為 complete，實際 cache 約 `5.07 GB`。
- **Delete→Install interaction blocker**：`on_cache_cleanup_finished()` 先排程 async inspection，再同步開
  blocking `Model Deleted` QMessageBox；modal 開啟期間背後已可顯示 Install，但第一個 click 只會被
  dialog 攔截，使用者必須關閉訊息再點一次。
- **Confirmation visual inconsistency**：Delete Model 與 Disable Assistant 仍使用平台 `Yes/No`
  QMessageBox，沒有 Settings 既有 danger/secondary palette、Confirm/Cancel hierarchy與一致 default
  focus。
- **Floating blocker**：點 Float 後整個 app 仍凍結。現有 real-dock heartbeat test 只使用 plain
  `QMainWindow` 與 offscreen Qt，沒有進入 product `MainWindow` 的 dock sizing/event-filter policy；產品
  shell 仍直接對 `QDockWidget` 設 minimum width，與 Qt 對 child-owned size constraints 的 contract
  衝突。上一輪延後 `setFloating()`、刪 geometry placement 與加入 manual system move 未解 native
  WSLg/xcb defect，因此不再以同類 callback 調整猜測原因。
- Branch 僅有 repo-root `settings.json` 的使用者本機修改，受保護且不得 stage、commit、revert或隱藏。

## Observable outcome

- Delete success 不開 modal；同一列完成 inspection 後明確顯示 `Not installed` 與 enabled
  `Install Model`，第一次 click 只產生一次 install request。Delete failure 才顯示錯誤。
- Delete Model 與 Disable Assistant confirmation 使用同一個 Settings-owned presentation：action-specific
  dangerous Confirm、neutral Cancel、Cancel default，顏色、hover、focus與目前 Settings theme一致。
- Download progress 不把 cache estimate 冒充精確完成率：傳輸中顯示 downloaded bytes／約略總量；達
  estimate 後切為 indeterminate `Finalizing and verifying model…`。只有 pinned snapshot validation與
  subprocess cleanup 都完成才可呈現 terminal success；180 秒沒有 cache-byte 成長時必須 bounded
  success recovery或typed timeout，不能等滿兩小時。
- Product runtime 在 Hugging Face import 前停用已於本機證實會 stall 的 Xet transport，使用可 resume 的
  standard HTTP path；不改 model、revision、cache boundary或 10/20 GB policy。
- WSLg/xcb 下 Float/Dock 連續 10 次、拖動、resize、Hide/Show、Settings與application close都保持 Qt
  heartbeat。先移除違反 Qt contract 的 dock-owned size constraint；若 exact native probe仍卡在
  `setFloating()`，QDockWidget收斂為 dock-only，AgentManager以一個 native-decorated view container移動
  同一份 ChatPanel/header，controller、conversation與runtime state不複製。

## Scope、ownership 與 non-goals

- `ModelDownloadLifecycle / ModelDownloader` 繼續擁有 download child、deadline、cleanup與 terminal；
  `ModelSettingsDialog` 只投影 state與發出既有 request；`AgentManager` 繼續擁有 dock/floating
  presentation。Owner before/after不變。
- 保留 `ModelDownloader.progress(int, str)` 與既有 public command contracts；不新增 model state machine、
  receipt、compatibility path、production module或 public class。
- 不改 Assistant tool calls、LLM controller、model choice、RAG policy、cache位置、EEG workflow或
  `settings.json`。CI不下載 5 GB model；真實 cold download由 exact-head manual acceptance證明。
- 優先刪除 blocking success modal、舊 `Yes/No` duplication、違規 dock constraint；只有 native matrix
  證明必要時才刪除 QDockWidget float/manual-drag path並換成單一獨立 container。
- 預期最多五個既有 production files；若 bug-fix production net LOC超過 300、觸及超過 8 files或新增
  production class/module，先回報 deletion candidates、owners與 LOC，再決定拆 PR。

## Ordered repair

1. 建立 exact red tests：delete success 無 blocking modal且首次 Install有效；兩個 confirmation 的
   action/cancel role與theme；estimated bytes到99後 stalled child必須 terminal；100不得早於 validation；
   product MainWindow＋AgentManager Float heartbeat而非 plain fixture。
2. 以 Settings 內部共用 confirmation builder 取代兩個 `Yes/No` call；success cleanup只觸發 inspection與
   inline state，不顯示 `Model Deleted`。
3. 在 desktop entry於任何 Hugging Face import前固定 `HF_HUB_DISABLE_XET=1`。保留 cache byte
   observability但改為 reviewed stage/bytes copy；加入180秒 inactivity budget。若 budget到期時 pinned
   snapshot已通過現有 validator，先 revalidate並發布 success；否則發布 timeout並沿用target-only cleanup。
4. 先用獨立process、5秒 timeout跑 WSLg/xcb matrix：plain/product MainWindow、default/custom title bar、
   dock constraint/child-only constraint，記錄 `setFloating` 前後 heartbeat。移除 MainWindow 對 dock 的
   minimum-width mutation並重測。
5. 若 step 4仍卡在 `QDockWidget.setFloating()`，執行已授權 fallback：QDockWidget dock-only；
   AgentManager-owned native floating container承載同一 ChatPanel/header；Float/Dock/Hide/toggle/window
   close/shutdown全由AgentManager路由，舊 `setFloating`、manual system move與duplicate float state刪除。
6. 重跑 identical focused tests、直接相鄰 UI/download lifecycle sweep、Ruff與Basedpyright。產生並由主
   agent查看 Settings confirmations、download terminal及 floating/docked candidates；只在要交使用者新
   exact source手測時再跑 applicable handoff workflow與required CI。

## Focused validation

- Unit：downloader、model download lifecycle、Model Settings、AgentManager、MainWindow dock policy。
- Lower-mock integration：spawned download child stall/reap/terminal；product MainWindow實際 container
  transition與Qt heartbeat；不以只驗 signal callback的mock取代。
- UI artifact：default scale＋320 px；loading、delete confirmation、disable confirmation、download
  finalizing、floating/docked states。Linux offscreen/xvfb不冒充WSLg或Windows native acceptance。
- Manual：同一 exact SHA 執行 delete→一次install、cold download terminal、兩個 confirmations、Float/Dock
  10 cycles與drag/resize/hide/show。Source再改即失效；使用者另行明確同意才可merge。

## Implementation checkpoint

- Exact red/green已完成：delete success不再開blocking modal；第一次Install會直接送出唯一request；Delete
  Model與Disable Assistant共用action-specific danger Confirm、neutral Cancel且Cancel為default/escape；實際
  screenshot確認top-level QMessageBox明確套用Settings palette。
- Download transport在desktop entry任何product/Hugging Face import前固定停用Xet；cache觀測改顯示bytes，
  estimate到99後切indeterminate finalizing。180秒無byte成長時，只有既有pinned snapshot validator通過才
  recovery success，否則typed timeout；lower-mock lifecycle已證明success terminal一定晚於child
  terminate/join/close。
- WSLg/xcb exact product MainWindow 10次Float/Dock、resize與hide/show heartbeat在30秒硬上限內通過；
  `setFloating()`不是目前阻塞點，未建立獨立視窗。真正拖曳風險收斂為上一輪新增的native
  `startSystemMove()` grab，該路徑與相關state已刪除，浮動窗只走既有pointer-delta move；dock minimum
  constraint也已從QDockWidget移回content-owned floor。
- 相鄰sweep為419 tests passed；Ruff check/format與targeted Basedpyright皆通過。ChatPanel UI/UX capture
  gate通過；主agent已查看520px installing、finalizing、advanced、Delete confirmation與Disable
  confirmation candidates，未見clipping、overflow或舊灰色danger action。
- Production觸及五個既有files，167 additions／92 deletions、net `+75` LOC；沒有新增module、public
  class、owner、state machine、receipt或compatibility path，未觸發complexity review。受保護的
  `settings.json`未修改或stage。
- PR #28遠端仍是舊head `202a7b53`；目前是local checkpoint。尚未以新exact source執行使用者cold
  install與Float/drag手測，故不稱handoff-ready、不合併。

## Stop conditions

- 若 standard HTTP cold download仍在180秒無byte progress後無法bounded terminal，保留checkpoint並記錄
  exact transport/child cleanup evidence，不以動畫或假100%掩蓋。
- 若 child被判 stalled但 snapshot validation不通過，不得發布success或保留為installed；只能typed
  failure與target-only cleanup。
- 若 child-only constraint後 native `setFloating()`仍凍結，禁止再堆疊timer/geometry/system-move補丁，
  直接走已授權獨立container fallback。
- 若任何 visual candidate未由主agent查看、required CI非success或新exact source未由使用者手測通過，
  不稱handoff-ready、不合入`main`。

長期目標讀 [Roadmap](roadmap.md)，evidence contract只讀 [Validation](../validation/README.md)。
