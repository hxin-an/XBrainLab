# XBrainLab Thesis Context

最後更新：`2026-05-01`

## 這份文件的用途

這份文件是給 agent 看的 thesis context，用來理解 XBrainLab 和碩論的關係。

它不是人類日常入口，也不是完整論文章節；只提供 agent 在整理文件、驗證 claims、規劃 tool-call agent 工作時需要知道的研究背景。

真正 source of truth：

- validation 邊界：`docs/validation/README.md`
- agent target：`docs/target/agent.md`
- agent current architecture：`docs/architecture/agent.md`
- thesis claim 相關決策：`docs/decisions/README.md`

## 目前論文主線

XBrainLab 目前支撐三條互相關聯的工作：

1. 穩定既有 PyQt EEG 分析應用。
2. 重設 app 內 tool-call agent 架構。
3. 建立足以支撐論文主張的驗證證據。

## 目前研究問題雛形

待整理成正式文字：

- 如何在既有科學桌面軟體中引入 workflow-aware tool-calling agent？
- 如何讓 agent 操作軟體能力面，而不是只成為聊天介面？
- 如何用可重現的工程驗證支撐 agent reliability / workflow success 的論文 claim？

## 工程和論文的邊界

工程和論文的 evidence 邊界以 `docs/validation/README.md` 為準。本文件不另存第二份判斷。

## 相關文件

- [Validation](../../docs/validation/README.md)
- [agent.md](../../docs/architecture/agent.md)
- [validation.md](../../docs/architecture/validation.md)
- [Decisions](../../docs/decisions/README.md)
