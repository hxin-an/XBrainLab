# XBrainLab Now

最後更新：`2026-08-26`

## 目前焦點

Data Import performance slice 停在 checkpoint；目前沒有 active product implementation。

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
