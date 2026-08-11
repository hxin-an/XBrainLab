# XBrainLab Agent Stack

最後更新：`2026-07-31`

這份文件只記錄「目前有效」的 agent 操作層。舊的 automation、role、skill、AQ queue 已整合到 canonical 文件或刪除。

## 現行 agent 文件

| 文件 | 用途 |
| --- | --- |
| `AGENTS.md` | repo 根層規則和最短閱讀入口。 |
| `.agents/README.md` | repo-local agent 操作入口。 |
| `.agents/stack.md` | 本文件；說明 agent 文件分工和有效能力。 |
| `.agents/runbooks/setup.md` | 現行 setup、工作規則、validation manifest routing。 |
| `.agents/runbooks/autopilot.md` | 長時間工作時的保守工作循環。 |
| `.agents/runbooks/architecture-review.md` | 全盤架構複盤步驟。 |
| `.agents/runbooks/refactor-gate.md` | 後端重構開工前 gate。 |
| `.agents/skills/README.md` | repo-local reusable skills 入口。 |
| `.agents/workflows/README.md` | repo-local workflows 入口。 |
| `.agents/context/project.md` | 專案接手脈絡與目前目標。 |
| `.agents/context/architecture-target.md` | 目標架構濃縮版。 |
| `.agents/context/thesis.md` | 給 agent 的碩論 context，只在 thesis / evaluation / agent claim 相關工作使用。 |

目前 active repo-local skills 在 `.agents/skills/`。

舊的 `xbrainlab-*` skills 已刪除，因為它們大量引用舊 `docs/current/*` 和 AQ queue。新的 skills 必須短、可重用、對齊目前 `docs/` canonical 文件。

active workflows 在 `.agents/workflows/`。workflow 是多步驟流程，skill 是可重用能力，不要混在一起。

## Source Of Truth

人類和 agent 都應以這些 canonical 文件為準：

1. `docs/current.md`
2. `docs/target/README.md`
3. `docs/architecture/README.md`
4. `docs/planning/now.md`
5. `docs/planning/roadmap.md`
6. `docs/decisions/README.md`
7. `docs/validation/README.md`

架構細節以 `docs/architecture/` 為準。舊設計文件已整合後刪除，不能當 current truth。

`.agents/context/` 只作導讀，不保存 current / target / architecture 的第二份 truth。

## Active Dispatch Authority

Agent 只能從以下三處取得目前施工順序和 completion contract：

1. `docs/planning/now.md`
2. `docs/agent_goals/product_quality_closure_goal.md`
3. `docs/records/product_quality_audit_2026-07-30.md`

`docs/current.md` 提供 current context；roadmap、records、worklog、artifact 和 Git history 提供
背景或 evidence。它們都不是第二份 active queue。若三個 active 入口彼此不一致，先停止
dispatch，依 source/runtime evidence 校準 canonical 文件。

## 目前階段

目前在 `integration/eeg-workflow-improvements-v1` 收斂 EEG workflow integration candidate。
這條線是 checkpoint，尚未 handoff-ready；`stabilize/product-quality-closure` 只保留為歷史
provenance，不是 active dispatch base。

這代表：

- legacy 文件已整合後刪除，不再保留 `docs/legacy/` 或 `.agents/legacy/` 閱讀面。
- backend `ApplicationService / Command API` 是唯一 product command spine；compatibility path
  不得用作 product success evidence。
- agent 必須依 active audit 收斂 UI/backend/assistant/validation findings，不得另建 queue。
- 弱測試或 compatibility-only 測試不得在較強 replacement coverage 落地前刪除。
- tool-call eval / thesis evidence 要等 active goal 關閉後再開始。
- milestone 是最低交付門檻，不是工作上限；完成後仍要主動修 bug、補測試、校準文件。

## 能力政策

- OpenAI、Codex、skills、plugins、automations 相關問題：用官方 OpenAI docs / `openai-docs` skill。
- MCP 已從 active XBrainLab roadmap 移除；只有使用者明確要求 MCP 時，才讀 MCP adapter / security skills。
- GitHub issue / PR / CI 相關問題：用 GitHub plugin 或 `gh`。
- XBrainLab repo-local skills：使用 `.agents/skills/` 內的 active skills；不要恢復舊 `xbrainlab-*` skills。
- 不新增新的 agent role 文件，除非使用者明確要恢復多角色 automation。

## 讀取順序

substantial work 前讀：

1. `AGENTS.md`
2. `docs/current.md`
3. `docs/planning/now.md`
4. `docs/agent_goals/product_quality_closure_goal.md`
5. `docs/records/product_quality_audit_2026-07-30.md`
6. `docs/target/README.md`
7. `docs/validation/README.md`
8. `.agents/runbooks/setup.md`
9. `.agents/runbooks/autopilot.md`
10. `.agents/skills/README.md`
11. `.agents/workflows/README.md`

需要論文或 agent product framing 時，再讀：

1. `.agents/context/thesis.md`
2. `docs/architecture/agent.md`
3. `docs/architecture/validation.md`

## 寫入規則

- 目前狀態寫 `docs/current.md`。
- 短期工作寫 `docs/planning/now.md`。
- 長期路線寫 `docs/planning/roadmap.md`。
- 決策寫 `docs/decisions/README.md`。
- 驗證邊界寫 `docs/validation/README.md`。
- 專業交接紀錄寫 `docs/records/implementation_log.md`。
- 流水帳寫 `docs/records/worklog.md`。
- agent 操作規則才寫 `.agents/`。
- 可重用 agent 能力寫 `.agents/skills/`。
- 多步驟 agent 流程寫 `.agents/workflows/`。

如果只是做一次驗證或踩坑，不要新開文件；先進 `docs/records/worklog.md`。

## 已退役

以下不再是 current control surface：

- `Prep Gate`
- `Repair Loop`
- `AQ-*`
- old `EXECUTOR / REVIEWER / idea-desk` heartbeat roles
- `docs/current/*`
- `docs/history/*`
- `docs/workflows/*`
- `docs/legacy/*`
- `.agents/legacy/*`
- old `/mnt/d/repos/XBrainLab` command paths
