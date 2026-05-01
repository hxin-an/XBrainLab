# Project Context

最後更新：`2026-05-01`

## 用途

這份 context 只提供接手背景與讀取方向，不保存 architecture truth。

真正 source of truth：

- 目前狀態：`docs/current.md`
- 目標需求：`docs/target/README.md`
- 目前架構：`docs/architecture/README.md`
- 短期工作：`docs/planning/now.md`

## 接手狀態

使用者接手 XBrainLab 時，專案缺乏可信文件，且前後端有閃退與不穩定問題。

接手後曾透過 agent / vibe coding 修了很長一段時間，因此 repo 內存在大量 AI / agent 產生文件。這些文件不一定錯，但不能直接信。

目前已完成第一輪文件清理：

- `docs/legacy/` 已刪除。
- `docs/active/` 已刪除。
- `.agents/legacy/` 已刪除。
- root `ROADMAP.md` 已刪除。
- canonical docs 已重新分層。

## 目前目標

目前目標以 `docs/current.md` 和 `docs/planning/now.md` 為準。本文件不重述細節。

## 使用者偏好

- 文件用中文，讀起來要快。
- 少數 canonical 文件，不要文件海。
- 能大改 AI 生成文件。
- 討論出來的決策要有固定地方。
- 短期工作和長期方向要分開。
- target / ideal architecture 不要混成 current truth。

## 工作邊界

工作邊界以 `docs/planning/now.md`、`docs/planning/roadmap.md`、`docs/decisions/README.md` 為準。
