# XBrainLab Agent Entry

最後更新：`2026-05-02`

這是 repo-local agent 操作入口。

## 先讀

1. `AGENTS.md`
2. `docs/current.md`
3. `docs/target/README.md`
4. `docs/architecture/README.md`
5. `docs/planning/now.md`
6. `.agents/stack.md`

## Agent 定位

本 repo 的 agent 不是口令執行器，而是 product-delivery engineering agent。
任務目標是把 XBrainLab 做成工程級可用的本地 EEG 桌面工具：backend 穩、UI 不閃退、agent 能可靠用 tool、本地 LLM 有可控路線、文件能交接。

Milestone 是最低交付門檻，不是只需要做這些。若 milestone 勾完但程式碼仍不可用、測試不能支撐、文件和現況不一致，工作沒有完成。

目前主線是 product delivery：

```text
backend core -> UI/agent command surface unification -> UI chat stabilization
-> agent tool alignment -> local LLM runtime -> desktop launcher
-> product stabilization -> tool-call eval
```

tool-call eval / thesis evidence 要等產品主線穩定後再開始。

## 不要做

- 不恢復 `.agents/legacy/`。
- 不恢復舊 `xbrainlab-*` repo-local skills。
- 不用舊 AQ / Prep Gate / Repair Loop queue。
- 不把 `docs/records/` 當 current truth。
- 不把 `target/` 當作已完成事實。
- 不把 milestone 當成工作上限。
- 不在產品主線不穩時提前做 tool-call eval。
- 不靠聊天回報保存狀態；重要狀態寫文件。

## Product Milestones

最低交付 milestone：

1. Backend product core。
2. UI chat / agent panel 成品化。
3. UI / agent command surface unification。
4. Agent tool system 成品化。
5. Local LLM runtime。
6. Desktop launch / packaging。
7. End-to-end product stabilization。
8. Tool-call eval / thesis evidence。
9. Final validation / documentation closure。

完成 milestone 時要自己判斷是否還有工程破洞；有就繼續修，不要把「通過最低清單」當成完成。

## 常用 runbooks

| 文件 | 用途 |
| --- | --- |
| `runbooks/setup.md` | 基本工作規則與驗證指令。 |
| `runbooks/autopilot.md` | 長時間工作循環。 |
| `runbooks/architecture-review.md` | 全盤架構複盤步驟。 |
| `runbooks/refactor-gate.md` | 後端重構開工前檢查。 |

## Skills / Workflows

| 路徑 | 用途 |
| --- | --- |
| `skills/` | 可重用能力，例如文件整理、架構複盤、驗證、重構切片、agent tool-call 設計。 |
| `workflows/` | 多步驟流程，例如 documentation review、architecture review、refactor slice、tool-call scoring。 |

## Context

| 文件 | 用途 |
| --- | --- |
| `context/project.md` | 接手脈絡與目前目標。 |
| `context/architecture-target.md` | 給 agent 的目標架構濃縮版。 |
| `context/thesis.md` | thesis / agent claim 相關背景。 |
