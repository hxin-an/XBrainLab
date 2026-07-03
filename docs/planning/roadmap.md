# XBrainLab Roadmap

最後更新：`2026-07-03`

這份 roadmap 是產品主線，不是施工日誌。它用來決定：**先做什麼，做到什麼程度才算過關，哪些 claim 不能先講。**

## 產品北極星

XBrainLab 要先成為一個能在 Windows 本地穩定操作的 EEG / BCI 桌面工具：

```text
啟動桌面 app
-> 解讀 EEG data / label / event
-> 使用者確認模糊語意
-> preprocess / epoch / dataset / train
-> evaluate / visualize
-> UI、assistant、scripts 看到同一份 workflow truth
```

MCP 已從 active product / thesis roadmap 移除。既有 MCP code、tests、artifacts 只保留為
歷史探索或相容性證據，不再是 MVP、release candidate、thesis evidence 或 handoff gate 的必要項目。

## MVP 包含什麼

| MVP 部分 | 完成後要能做到 |
| --- | --- |
| 0 Current Truth Rebaseline | 文件、分支、known blockers、validation claim 和 artifact freshness 可理解。 |
| 1A Backend / UI Stabilization | 主要產品路徑走 `ApplicationService / Command API`；legacy fallback 和 duplicate refresh truth 不再是正式成功路徑。 |
| 1B Data Interpretation MVP Slice | 使用者能處理代表性的 label / event / trigger ambiguity，並把 import recipe 交給 epoch / training。 |
| 1C In-App Assistant Product Baseline | assistant 使用 backend state、capability policy、verification boundary 和 structured command result。 |
| 1D Windows Desktop Acceptance | 人能在 Windows 桌面完成代表性 EEG workflow。 |

MVP 之後才做 release candidate 和 formal thesis evidence。

## 階段表

| Phase | 重點 | 完成判準 | 不能宣稱 |
| --- | --- | --- | --- |
| 0 Rebaseline | 重新盤點現況、文件、分支、artifacts、known blockers。 | `current / now / roadmap / architecture / validation` 不互相矛盾；MCP 從 active plan 移除。 | product complete。 |
| 1A Backend / UI Stabilization | command spine、legacy cleanup、UI refresh、test cleanup、runtime crash / layout blocker。 | 主要 mutating product path 可追到 command route；手測前 gate 不只靠 dashboard。 | 所有 controller 都消失。 |
| 1A-V Validation Reality Gap | 盤點現有測試與實機體驗落差。 | test matrix 清楚標出 unit / integration / screenshot / launcher / human-observable smoke 能抓什麼；至少一條代表性桌面 workflow 有可重跑 product smoke。 | dashboard PASS 等於產品可用。 |
| 1B Data Interpretation | 新資料入口可用。 | wizard 可 preview / validate / confirm / apply 代表性資料語意。 | 支援所有格式或 final import system。 |
| 1C Assistant Baseline | in-app assistant 不走旁路。 | readiness、blocked reason、confirmation boundary、structured result 和 UI backend truth 一致。 | formal thesis benchmark 完成。 |
| 1D Desktop MVP | 人手 Windows workflow 驗收。 | launcher -> import -> preprocess -> train -> evaluate / visualize 可完成。 | signed installer 或 release approval。 |
| 2 Release Candidate | 可下載測試版與限制說明。 | candidate artifact、version、known limitations、troubleshooting。 | 每次 merge 自動正式發布。 |
| 3 Thesis Evidence | formal agent / tool-call 評估。 | case suite、model、repeat count、scorer version、dataset protocol、failure taxonomy 都清楚。 | agent score 代表 UI 完成。 |

## Phase 3 的特別說明

Phase 3 是論文 evidence 階段，不是目前產品修復階段。正式擴充 tool-call benchmark 之前，
XBrainLab 本體、assistant command path、verification layer 和代表性產品 workflow 必須先穩定。

Benchmark case generation 啟動時應採用 AutoResearch-style 流程：先研究 tool-call /
agent trajectory benchmark 方法、XBrainLab workflow 和 EEG / BCI 使用情境，再產生候選 cases。
候選 cases 不能直接成為 gold benchmark；必須由主 agent 去重、檢查 coverage、審核 expected
tool / state / verification 行為，並凍結成可重跑 suite 後才可支撐 thesis claim。

## MCP 決策

MCP 不再是 active roadmap。

- 不再規劃 MCP hardening phase。
- 不再把 MCP client certification 當 release 或 thesis 前置。
- 不再要求每個 backend / UI / assistant handoff 都跑 MCP gate。
- 既有 MCP 相關 records 保留在 git history / records，作為過去探索，不作為下一步工作。

如果未來重新啟用 MCP，必須另開 decision，重新定義 scope、security、session ownership、
client matrix 和 validation cost；不能從舊 roadmap 自動復活。

## Phase 1A 的特別說明

這一段是 MVP 前置，不是可有可無的重構。

`BackendFacade` 已從 product code 移除；Phase 1A 的邊界現在是防止它回來：

- assistant / script 直接使用 `ApplicationService / Command API` 或薄 command adapter。
- 舊 facade 行為只能保存在 command/service/helper replacement coverage。
- 不替 UI / assistant / scripts 維護另一套 state truth。

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

- MCP hardening / MCP client certification。
- signed installer / notarization。
- formal thesis benchmark refresh。
- full local model x3 release gate。
- Expert Workflow Mode。
- Workflow Recipe DSL。
- Training Model Registry / Model Node Visualization。
