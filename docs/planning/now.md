# XBrainLab Now

最後更新：`2026-07-03`

這頁只放下一輪施工焦點。

## 目前焦點

**Current truth rebaseline before more feature work.**

最近幾週產品、UI、saliency、Data Import、agent / thesis discussion 都有推進，但 canonical docs
沒有跟著每個 checkpoint 收乾淨，導致 roadmap、current state、artifact claim 和實際分支狀態重新變得難判斷。

現在先做文件與狀態重盤點，再繼續推進功能。這不是暫停工程，而是避免在錯誤前提上繼續疊工作。

## 本輪 To-do

| 狀態 | 工作 | 完成判準 |
| --- | --- | --- |
| In progress | Current docs rebaseline | `docs/current.md`、`docs/planning/now.md`、`docs/planning/roadmap.md`、`docs/architecture/README.md`、`docs/validation/README.md` 對目前方向不矛盾。 |
| In progress | MCP 從 active plan 移除 | Roadmap、current truth、target / architecture docs 不再把 MCP 當 MVP、release、thesis 或 handoff gate。 |
| In progress | Roadmap 心智模型定型 | Roadmap 改成 Rebaseline -> Desktop MVP -> Product Polish / Release Candidate -> Assistant MVP -> Thesis Evidence；UI/UX blocker 放進 Desktop MVP，視覺一致性放進 Product Polish。 |
| Pending | Branch / worktree inventory | 列出目前可作為下一輪手測或整合基底的分支；舊 worktree / branches 只清掉已確認不需要的，不做 destructive reset。 |
| Pending | Known blocker reset | 重新列出使用者最近手測提到的 UI / runtime blocker：evaluation、visualization、model selection scroll、3D centering、saliency readiness、Data Import label reload。 |
| Pending | Handoff gate reset | 重新確認「可以給使用者手測」前必跑的 happy path、edge case、多資料集、screenshot artifact 和 claim boundary。 |
| Deferred | New feature work | 在 current truth、branch base 和 known blockers 重新對齊前，不再開大型 UX 或 assistant feature slice。 |

## 為什麼文件更新會停掉

文件不是沒價值，而是流程上沒有被強制放進每個 checkpoint gate。近期很多工作以 bugfix branch、
artifact refresh、聊天中狀態回報為主，`worklog` 和 screenshots 有更新，但 `current / now /
roadmap / architecture` 沒有每次同步，所以 canonical truth 慢慢落後。

新規則：

- 每個 handoff candidate 都要更新 canonical docs 或明確說「不需要更新，原因是什麼」。
- artifact 更新不能取代 `docs/current.md`。
- branch push / tests green 不能取代 `docs/planning/now.md`。
- roadmap 決策變更要寫入 `docs/planning/roadmap.md` 和 `docs/decisions/README.md`。

## 本輪不做

- 不重開 Match Labels / Review and Import 大型 UX 設計。
- 不做 MCP hardening、MCP client certification 或 MCP thesis evidence。
- 不開始 thesis-grade agent benchmark 實驗；那需要獨立 research branch / goal。
- 不把 automated dashboard PASS 當作 human Windows acceptance。
- 不把舊 artifact 當成 current truth。

## 收尾條件

本輪可以收尾的條件是：

1. MCP 已從 active docs 和 gate 語意移除。
2. Roadmap 五階段心智模型已寫進 canonical docs。
3. `mkdocs build --strict` 通過。
4. `git diff --check` 通過。
5. docs branch clean commit 並 push。
6. 下一輪工程入口清楚：哪個分支、哪些 blocker、哪些 gate、哪些文件要同步。
