# XBrainLab Now

最後更新：`2026-07-31`

這頁只保存 active delivery context、近期施工順序和 exit condition。Finding status 以
[Product Quality Audit](../records/product_quality_audit_2026-07-30.md) 為準，不在這裡複製
第二份 queue。

## 目前焦點

**Close product-quality findings on one integration line, rebuild exact-commit evidence, then
decide whether a Windows handoff candidate exists.**

目前不是 handoff-ready。`ux/assistant-product-v1@3869aaef` 只作 baseline；所有 closure work
都在 `stabilize/product-quality-closure`。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Worktree | `/mnt/d/workspace_v2/projects/lab/xbrainlab/build/worktrees/assistant-product-v1` |
| Branch | `stabilize/product-quality-closure` |
| Baseline | `ux/assistant-product-v1@3869aaef73acf3fb30ce95d15868c2abcf17c6f5`，baseline only |
| Goal | `docs/agent_goals/product_quality_closure_goal.md` |
| Ledger | [Product Quality Audit - 2026-07-30](../records/product_quality_audit_2026-07-30.md) |
| Current classification | `checkpoint` / closure in progress |

不要從舊文件推論 registered worktree 數量。需要 inventory 時執行
`git worktree list --porcelain`；其他 worktree 不得被誤認成 active candidate，也不得覆寫其
owner 的 dirty changes。

## 施工順序

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 1 | Close code-controllable P0/P1 findings | Ledger 中相關 row 有 implementation、focused regression、same-class sweep 和主 agent verification；不能只改 status。 |
| 2 | Preserve architecture boundaries | Product path 維持 `ApplicationService / Command API`；`BackendFacade` 保持物理移除；UI、agent、headless 不建立第二套 capability/state truth。 |
| 3 | Rebuild functional evidence | Real ApplicationService FIF-to-visualization smoke、deterministic oracle、strict fixture manifest 和 required multi-dataset gates 從 current source 通過。 |
| 4 | Rebuild assistant and UI evidence | Exact Granite / secure offline RAG、error/retry/cancel/long-session，以及 full/narrow/DPI screenshots 綁定相同 source identity，並由主 agent 檢查。 |
| 5 | Close docs/repository findings | Canonical current、planning、validation、handoff 和 skill truth 一致；stale baseline/historical totals 不再呈現成 current result。 |
| 6 | Final exact-commit gate | 同一 clean pushed commit 跑 handoff dashboard、static checks、regression、MkDocs、reviewer re-gates；generated report identity 完整吻合。 |
| 7 | Windows acceptance | 只有前一步成立後才能稱 Windows handoff candidate；真人 acceptance 完成前不合併 `main`、不稱 product complete。 |

## Evidence Rule

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

達成以上條件後，狀態只能提升為 **Windows handoff candidate**。真人 acceptance 之前仍不是
product complete。

## 本輪不做

- 不把 baseline branch fast-forward 或重新命名成 current candidate。
- 不新增 facade、silent compatibility fallback 或第二套 workflow truth。
- 不做 MCP hardening、MCP client certification 或 MCP thesis evidence；除非使用者明確要求。
- 不在產品 closure 完成前 freeze thesis benchmark 或宣稱 raw-model accuracy。
- 不把 automated dashboard、offscreen screenshots 或 launcher smoke 當成人工 acceptance。
- 不新增 planning 文件；新 current truth 回寫既有 canonical pages。
