# XBrainLab Now

最後更新：`2026-08-08`

這頁只保存 active delivery context、近期施工順序和 exit condition。舊
[Product Quality Audit](../records/product_quality_audit_2026-07-30.md) 保留為此次 main checkpoint
的歷史 ledger，不再作為新的 active queue。

## 目前焦點

**以已合併的 `main` GUI checkpoint 為產品基線，先關閉五項 EEG workflow 改進的整合候選，
再繼續效能與簡化 Assistant prototype。**

目前不是 release 或 Assistant handoff-ready。真人資料驗收只涵蓋 Graz 2a GDF 與 OpenNeuro
ds003061 P300 BIDS 各一個資料集；其餘格式、自動化 evidence 與舊 Agent gate 不可外推。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Worktree | 以目前 `main` checkout 的 `git rev-parse --show-toplevel` 為準。 |
| Product baseline | `main` |
| Candidate branch | `integration/eeg-workflow-improvements-v1`；五項 EEG workflow 改進的未合併整合候選。 |
| Baseline | `ux/assistant-product-v1@3869aaef73acf3fb30ce95d15868c2abcf17c6f5`，baseline only |
| Goal | 老師試用前 GUI/data stabilization；其後是 performance 與 simplified Assistant prototype。 |
| Historical ledger | [Product Quality Audit - 2026-07-30](../records/product_quality_audit_2026-07-30.md) |
| Current classification | merged development checkpoint；not release / not Assistant-ready |

不要從舊文件推論 registered worktree 數量。需要 inventory 時執行
`git worktree list --porcelain`；其他 worktree 不得被誤認成 active candidate，也不得覆寫其
owner 的 dirty changes。

## 施工順序

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 1 | Stabilize teacher-facing GUI/data flow | 針對 GDF、BIDS 與老師新增資料逐一走 import -> preprocess -> epoch -> training；發現 blocker 就用 focused regression 修正。 |
| 1a | Review EEG workflow improvements candidate | 檢查 Braindecode catalog、BIDS subject preselection、test curve、Evaluation / Saliency cross-fold summary 與 Normalize 的 exact-head CI、Windows UI 與資料語意；通過前不合併。 |
| 2 | Measure and polish performance | 對 load、publication refresh、plots、preprocess 與 training startup 記錄 latency / UI heartbeat；不以主觀「看起來快」結案。 |
| 3 | Simplify Assistant prototype | 移除要求使用者先理解 Single step / Workflow 的心智負擔；由自然語言決定執行範圍，重要操作仍遵守 confirmation policy。 |
| 4 | Recalibrate Agent gates | 盤點並修改舊 prompt/tool/gate assumptions；建立與目前 Assistant UX、Granite 2B、真實 GUI state 一致的可重跑 gate。 |
| 5 | Expand dataset acceptance | 每新增一個真人資料集都記錄來源、格式、label semantics、可完成步驟與限制；不同副檔名不冒充不同資料集。 |
| 6 | Candidate gate | 在明確候選 commit 跑 relevant regression、multi-dataset、UI artifact、static/docs 與真人 Windows acceptance，再決定 release claim。 |

## Evidence Rule

本候選的 immediate exit signal 是：五項 focused suites、populated `All Folds` Evaluation / Saliency
artifact、exact-source manifest、required multi-dataset、strict docs/static、configured upstream 與
exact-head CI 全部可追溯到同一 commit。現有 tracked screenshots 只能支撐 layout checkpoint。

Final totals 不能從本頁、聊天、checkpoint notes 或多次局部 pytest output 手動加總。
唯一可用的 final totals 是同一 clean exact commit 產生的 handoff evidence，且至少要記錄：

- profile；
- worktree / branch；
- full commit SHA；
- dirty / protected-local state；
- command、return status、skip / xfail / deselection policy；
- artifact source identity 和 reviewer verdict。

`artifacts/quality/latest.md` 必須逐欄檢查 identity。若仍指向
`ux/assistant-product-v1@3869aaef`、dirty tree 或不同 commit，它只能算 baseline /
checkpoint evidence。

## Handoff Exit Condition

必須同時成立：

1. Audit 中沒有 code-controllable P0/P1 open item。
2. Focused regression、same-class/source guards、real happy path、deterministic oracle 和 strict
   multi-dataset gate 均由 final commit 重跑。
3. Granite/RAG 和 UI artifacts 是 exact-source output，必要畫面由主 agent 逐張檢視。
4. Ruff、完整 configured product-source Basedpyright、architecture checks、relevant pytest、`mkdocs build --strict` 和
   handoff dashboard 全部來自同一 commit。
5. Branch 已 push；worktree clean，或只保留規則允許且未 stage 的 protected local settings。
6. Final report 明確列出 Windows DPI/multi-monitor、interactive 3D、teacher datasets 和
   long-session 等剩餘人工風險。

達成以上條件後，狀態才能提升為下一個 **Windows handoff candidate**。目前 `main` 只是已接受
的開發 checkpoint，仍不是 product complete。

## 本輪不做

- 不把 baseline branch fast-forward 或重新命名成 current candidate。
- 不新增 facade、silent compatibility fallback 或第二套 workflow truth。
- 不做 MCP hardening、MCP client certification 或 MCP thesis evidence；除非使用者明確要求。
- 不在產品 closure 完成前 freeze thesis benchmark 或宣稱 raw-model accuracy。
- 不把 automated dashboard、offscreen screenshots 或 launcher smoke 當成人工 acceptance。
- 不新增 planning 文件；新 current truth 回寫既有 canonical pages。
