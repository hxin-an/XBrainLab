# XBrainLab Roadmap

最後更新：`2026-05-10`

這份 roadmap 是產品主線，不是施工日誌。它用來決定：**先做什麼，做到什麼程度才算過關，哪些 claim 不能先講。**

## 產品北極星

XBrainLab 要先成為一個能在 Windows 本地穩定操作的 EEG / BCI 桌面工具：

```text
啟動桌面 app
-> 解讀 EEG data / label / event
-> 使用者確認模糊語意
-> preprocess / epoch / dataset / train
-> evaluate / visualize
-> UI、assistant、MCP、script 看到同一份 workflow truth
```

## MVP 包含什麼

| MVP 部分 | 完成後要能做到 |
| --- | --- |
| 1A Backend Command Spine Cleanup | 主要產品路徑走 `ApplicationService / Command API`，legacy fallback 不再是正式成功路徑。 |
| 1B Data Interpretation MVP Slice | 使用者能處理代表性的 label / event / trigger ambiguity。 |
| 1C Tool-Call Product Baseline | assistant / MCP 使用同一套 backend state、capability policy、command result。 |
| 1D Windows Desktop Acceptance | 人能在 Windows 桌面完成代表性 EEG workflow。 |

MVP 之後才做 release candidate、formal thesis evidence、完整 MCP client certification。

## 階段表

| Phase | 重點 | 完成判準 | 不能宣稱 |
| --- | --- | --- | --- |
| 0 Repo / CI | branch、PR、CI、Git 狀態可理解。 | checks green，沒有 merge conflict，dirty local settings 不混進 commit。 | product complete。 |
| 1A Backend Cleanup | command spine、legacy cleanup、UI refresh、test cleanup。 | 主要 mutating product path 可追到 command route；測試不保護第二套 workflow truth。 | 所有 controller 都消失。 |
| 1A-V Validation Reality Gap | 盤點現有測試與實機體驗落差。 | test matrix 清楚標出 unit / integration / screenshot / launcher / human-observable smoke 能抓什麼；至少一條代表性桌面 workflow 有可重跑 product smoke。 | dashboard PASS 等於產品可用。 |
| 1B Data Interpretation | 新資料入口可用。 | wizard 可 preview / validate / confirm / apply 代表性資料語意。 | 支援所有格式或 final import system。 |
| 1C Tool-Call Baseline | assistant / MCP 不走旁路。 | readiness、blocked reason、structured result 和 UI backend truth 一致。 | formal thesis benchmark 完成。 |
| 1D Desktop MVP | 人手 Windows workflow 驗收。 | launcher -> import -> preprocess -> train -> evaluate / visualize 可完成。 | signed installer 或 release approval。 |
| 2 Release Candidate | 可下載測試版與限制說明。 | candidate artifact、version、known limitations、troubleshooting。 | 每次 merge 自動正式發布。 |
| 3 Thesis Evidence | formal agent / tool-call 評估。 | case suite、model、repeat count、scorer version 都清楚。 | agent score 代表 UI 完成。 |
| 4 MCP Hardening | 外部 agent adapter 成熟化。 | session ownership、auth、job lifecycle、client matrix。 | headless MCP 等於控制使用者桌面 UI。 |

## Phase 1A 的特別說明

這一段是 MVP 前置，不是可有可無的重構。

`BackendFacade` 可以保留，但它的角色必須明確：

- assistant / script 的 high-level convenience wrapper。
- `ApplicationService / Command API` 的入口包裝。
- 不自己重做 workflow logic。
- 不替 UI / agent / MCP 維護另一套 state truth。

如果 `BackendFacade`、UI controller fallback、test adapter 任一方開始定義自己的 workflow 成功條件，
Phase 1A 就還沒完成。

## Phase 1A-V 的特別說明

這一段不是新增功能，而是修正 validation strategy 本身。

目前已知風險是：工程測試可以證明 command lifecycle、widget render、architecture guard 和
startup baseline，但仍可能漏掉人手實機才會遇到的問題，例如視窗跑出螢幕、primary action 被長
preview 擠掉、scan scope 洩漏成 confusing UI、或 WSLg / Qt backend 偶發 segfault。

完成 Phase 1A-V 前，任何 dashboard PASS 都只能說 engineering baseline clean，不能說 product
workflow usable。

## Not Now

- signed installer / notarization。
- formal thesis benchmark refresh。
- full local model x3 release gate。
- Expert Workflow Mode。
- Workflow Recipe DSL。
- Training Model Registry / Model Node Visualization。
