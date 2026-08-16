# XBrainLab Now

最後更新：`2026-08-16`

## 目前焦點

**收尾 `assistant/toolbar-floating-polish-v1` / PR #28：保留可續傳的 model partial cache、
將 Assistant 收旂為固定右側 panel，並在新 exact source 手測通過前不合併。**

使用者已於 `2026-08-16` 明確授權本輪 UI 修改，並選擇：

- Hugging Face standard HTTP 讀取 timeout 提高為 60 秒，保留外層 180 秒無 byte
  成長的 bounded terminal；
- timeout、network failure 或 Cancel 後保留 partial cache 供 Retry 續傳；只有明確
  Delete 或資源 policy 阻擋才清理；
- 取消 Float 功能，Assistant 固定在主視窗右側。

## 問題與證據

- 本次 Granite 安裝遇到 `us.aws.cdn.hf.co` standard HTTP `Read timed out` 後多次
  `Trying to resume download...`。Hugging Face Hub 0.36.0 預設 download read timeout 為 10 秒；
  任一 chunk 成功又會重置 retry，不穩定連線可長時間反覆 resume。
- 使用者最後已重新下載成功；目前 pinned revision
  `707f574c62054322f6b5b04b6d075f0a8f05e0f0` cache 約 5.07 GB，現有 product validator
  已通過，不需要刪除或重新下載。
- `ModelDownloadLifecycle` 在失敗或 Cancel 後會自動遞迴刪除 target partial cache，
  讓 Hugging Face 原本的 cross-attempt resume 失效，並多出 pending outcome/cleanup state。
- WSLg 實際操作 Float 仍反覆凍結。現有路徑包含 button、icon、manual drag、
  double-click、transition flag、dock top-level signals 與 MainWindow sizing 分支；使用者已取消
  此功能，不再繼續疊疊 native workaround。
- Worktree 只有 repo-root `settings.json` 是使用者本機 runtime 修改；不得 stage、
  commit、revert 或隱藏。

## Observable outcome

- GUI entry 在任何 product/Hugging Face import 前預設 `HF_HUB_DOWNLOAD_TIMEOUT=60`，並
  繼續停用已在 WSLg stall 的 Xet transport。
- Download child 終止並被 reap 後才發佈 terminal。Failed/timeout/cancelled target partial
  保留在同一 cache path；Retry 使用同一 model/revision/path，但只有 complete pinned
  snapshot validation 通過才顯示 Installed。
- Explicit Delete 仍只刪除選定 model target；10 GB single-model、20 GB total-cache 與磁碟預留
  policy 不變。
- Assistant 是 right-only QDockWidget；無 Float/Dock button、無拖曳/雙擊切換、無 left
  docking。Header 只有 New Chat、Settings、Hide，Hide/Show/resize/close 不會變成
  floating window。

## Scope、ownership 與 non-goals

- `ModelDownloadLifecycle / ModelDownloader` 仍是 download child、deadline、validation 與 explicit
  deletion owner；不新增 state machine、receipt、module 或 public class。
- Owner before：AgentManager、QDockWidget 與 MainWindow 共同處理 float transition/sizing。Owner after：
  AgentManager 建立固定右側 dock，MainWindow 只依 visibility 處理 shell width；沒有 floating
  lifecycle owner。
- Deletion candidates：float/dock button、icons/assets、manual title drag/double-click、transition state、
  top-level callbacks、float-only capture/test paths，以及 failed/cancelled automatic cleanup reason/pending outcome。
- 不改 model、revision、cache location、Assistant controller/tool calls/RAG/EEG workflow 或
  `settings.json`。不在 CI 重下 5 GB model。
- 使用 skill 時實際暴露的 `tdd-guard` / `refactor-slicer` workflow 相對路徑斷鏈依使用者
  明確要求同步修正；只改這兩個 locator，不擴張為 guidance 全盤審查。
- 本 slice 預期使用現有 production files 並淨減 LOC；若反而觸發 complexity threshold，
  停止並重新拆分。

## Ordered repair

1. 新增 exact red tests：failed/timeout/cancelled 後 partial 存在且 lifecycle terminal；固定右側
   dock 不得 movable/floatable，header 無 float action。
2. 刪除 unsuccessful-download automatic cleanup reasons、pending outcome 與 cleanup branches；explicit
   `USER_DELETE` 仍使用既有 background cleanup owner。
3. 在 desktop entry 加入 60 秒 Hugging Face read timeout，順序必須早於任何 product
   import；保留 180 秒 inactivity 與 two-hour absolute deadline。
4. 刪除 Float 產品路徑、assets與不再可達的 branches；MainWindow/capture 改為固定右側
   invariant。
5. 更新 directly relevant tests、approved UI baseline 與 `docs/architecture/ui.md`，產生並
   實際查看 default-scale/narrow-width artifact。
6. 修正兩個 repo-local skill 對 canonical workflow 的相對路徑，並以 locator existence guard
   驗證。
7. 跑 focused unit/integration、Ruff、Basedpyright 與 applicable CI；交付新 exact SHA 給使用者
   手測，批准前不合併。

## Focused validation

- TDD red/green：`test_model_download_lifecycle.py`、`test_run_splash_geometry.py`、AgentManager/
  Assistant toolbar/MainWindow dock policy tests。
- Same-class sweep：downloader inactivity/reap/validator，explicit model deletion，Settings retry/cancel，
  product walkthrough 與 fixed-dock recovery capture。
- UI artifact：default scale 與 320 px 最小寬度，查看 header 操作、Settings、Hide/Show 與
  無 clipping/overlap；Linux/WSL automated artifact 不取代 native manual acceptance。
- Manual exact SHA：Settings 顯示已完整安裝而不啟動下載；Local Assistant 回答一個
  簡單問題；panel 始終固定右側，Settings、Hide/Show 與關閉程式皆可終止。

## Implementation checkpoint

- Exact red/green 已完成：舊 lifecycle 會在 failed/cancelled terminal 後刪除 partial cache；
  新 contract 保留同一 model/revision/path 並由 Retry 續傳，explicit Delete 仍走既有
  target-only background cleanup。Desktop entry 也已鎖定 product import 前設定 60 秒
  Hugging Face read timeout。
- Assistant 已收斂為 fixed-right dock；Float/Dock actions、兩個 SVG、manual drag/double-click、
  top-level transition state/callback 與 MainWindow floating sizing branch 都已刪除。Header 只保留
  New Chat、Settings、Hide。
- Focused unit/integration sweep 為 433 passed；後續單點 MainWindow regression 為 1 passed。
  Ruff check/format、targeted Basedpyright、`git diff --check` 與 agent guidance audit 均通過。
- ChatPanel recovery artifact 已實際查看 420 px、320 px 與 Settings ready states；canonical UI
  baseline 重新產生並 validate，7 artifacts 全部通過，最大 mean diff 0.305、changed 0.90%，
  Assistant approved reference 已更新為 fixed-right header。這是 Linux offscreen evidence，
  不取代使用者 native 手測。
- Production 觸及 9 個既有 paths（其中兩個是刪除的 SVG），23 additions／245 deletions，
  net `-222` LOC；沒有新增 module、public class、owner、state machine、receipt 或 compatibility
  path，符合 deletion-first。兩個 skill 的 canonical workflow locator 已修正，guidance audit 通過。
- 受保護的 root `settings.json` 仍是使用者既有本機修改，未被本 slice 修改、stage 或隱藏。
  MkDocs strict build 已通過。目前仍是未提交 checkpoint；尚缺 exact commit/CI 與使用者手測，
  因此不稱 handoff-ready、不合併。

## Stop conditions

- Partial cache 不得被當成 Installed；validator 未通過只能顯示 Retry/failure。
- 若保留 partial 導致 retry 新增第二份 cache truth、繞過 resource policy 或無法
  explicit Delete，停止並修正，不加 compatibility state。
- 若 fixed-right 後仍有任何 reachable `setFloating()`/manual drag/Float action，不交付手測。
- 若 artifact 未由主 agent 查看、required CI 未 success 或新 exact source 未由使用者手測
  通過，只稱 checkpoint，不合入 `main`。

本 branch 完成後才從合併後 `main` 建立獨立 Agent real-runtime smoke slice；不在本 UI/
download diff 修改 Assistant controller 架構。

長期目標讀 [Roadmap](roadmap.md)，evidence contract只讀 [Validation](../validation/README.md)。
