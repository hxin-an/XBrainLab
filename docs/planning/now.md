# XBrainLab Now

最後更新：`2026-08-27`

## 目前焦點

### UI health boundaries

- 問題與證據：`ChatComposer` 在 IME preedit Enter 路徑直接解參考 optional
  `QGuiApplication.inputMethod()`；`MainWindow` 重複解參考 stub 視為 optional、但 Qt 保證存在的
  status bar；`update_info_panel()` 仍保留 production 不再建立的 direct `info_panel` fallback。
- Outcome：IME service 不可用時第一次 Enter fail closed 且可恢復；status bar 行為不變；資訊刷新只由
  `InfoPanelService` 擁有。這個 slice 不改 layout、文案、tool contract 或資料流程。
- Scope／non-goals：只修改 composer、MainWindow 與直接測試；不重建 Basedpyright baseline、不整理其他
  compatibility hook、不調整 Electrode Layout PR。已取得使用者 UI 修改確認。
- 修理步驟：先建立 IME unavailable red test 與既有 status/info characterization，再做最小修正、刪除
  legacy fallback test，最後跑 focused tests、static gates、canonical handoff、PR/CI。
- Stop condition：同一 clean/explained exact commit 的 applicable gates 與 artifacts 完成後交 WSLg
  注音／Enter、status bar、資訊刷新手測；任何 source 再改即重跑。若 Basedpyright 只因行位移誤判，
  不改 baseline，另開 validation repair。

Data Import performance slice 維持 checkpoint，不在本次 UI health scope 內。

### Checkpoint evidence

- 在 WSL `/mnt/d` 的 OpenNeuro ds003061 `sub-001`（一次 warm-up、三次 fresh
  `ApplicationService` catalog → review → apply → background idle）中，final net `-5` candidate
  blocking median 是 `12.046162s`，background median 是 `1.530436s`，stable-idle median 是
  `13.558181s`。10 秒 performance gate 未通過。
- exact `31b79daf` read-only audit：Review 約 `4.6s`，有 241 次 `resolve`、627 次 `stat`；
  `_scan_after_resource_preflight` cumulative `3.523s`，兩次 `bids_summary` cumulative
  `1.534s`。`/mnt/d` repeated `lstat` 是 dominant cost；約 190 MB 的 Review identity hash、
  EEGLAB load 與 session copy 不是主因。
- 新 characterization 證明 preflight BIDS summary（`materialize=False`、無 metadata guard）與
  admitted materialization（`materialize=True`、有 admitted guard）是不同安全階段；後者才可
  產生 participants／sidecar metadata。symlink/containment 行為維持既有 focused test。
- 因此不能安全 deduplicate：preflight 的 layout/events/channels selected scope 是 resource
  admission 輸入；以 materialized output 取代它會倒置 admission，重用 preflight output 會讓
  未 admitted metadata 進入 candidate。沒有 production change。
- Apply final full rehash 與 `SourceFileBoundary` 維持必要安全邊界；不為速度弱化它們。

### Next handoff

- 依使用者要求，下一步將目前 baseline 做 exact-source handoff：clean/explained exact source
  commit 後執行 canonical handoff manifest、source-diverse dataset gate、push PR/CI，再交 WSLg
  使用者手測與明確 merge approval。
- 已知限制是 blocking 約 `12.046s`；不宣稱 performance gate 達成或 handoff-ready。root
  `settings.json` 是使用者本機設定，不納入此 slice。
