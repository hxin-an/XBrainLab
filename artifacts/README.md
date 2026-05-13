# XBrainLab Artifacts

最後更新：`2026-05-14`

`artifacts/` 放的是機器產物：dashboard、截圖、walkthrough、eval output、packaging evidence。
它們是 evidence，不是 current truth。

目前真相請看 `docs/current.md`；evidence 怎麼解讀請看 `docs/validation/README.md`。

## 使用規則

- artifact 可以支撐它實際跑過的範圍。
- artifact 不能自動擴張成 product complete、human acceptance 或 thesis claim。
- 不手改 generated artifact 來讓結果看起來更好。
- 如果 artifact 和 current docs 衝突，先查 source / runtime，再更新 canonical docs 或重跑 artifact。
- artifact 不應變成第二套文件系統；過期 handoff、被較完整 walkthrough 覆蓋的截圖族群、
  或可由 generator 重建的 duplicate snapshot，應保留在 git history，不長期留在 current tree。
- current tree 只保留「需要被現在讀者判讀」的 evidence 入口；探索型、affected-case、
  guardrail-only、或已被 full dashboard / consolidated walkthrough 覆蓋的 artifact，保留在
  git history，不再保留一份目前副本。

## 主要 artifact family

| Family | 用途 | 不能代表 |
| --- | --- | --- |
| `quality/` | fast engineering dashboard。 | product complete。 |
| `ui/human-like-walkthrough/` | automated PyQt walkthrough、截圖、按鈕狀態。 | human Windows desktop acceptance。 |
| `agent_evals/` | tool-call benchmark / scorer output。 | UI usability 或 EEG training quality。 |
| `mcp/` | MCP stdio / HTTP adapter walkthrough。 | 完整 MCP client certification。 |
| `data_interpretation/` | format capability matrix、internal-event preview evidence。 | 所有 EEG 格式完整支援，或數字 event code 的真實 class semantics。 |
| `ui/data-import-wizard-steps/` | Data Import wizard minimal review screenshots plus placement panels。 | final Match Labels / Review and Import UX，或 human Windows acceptance。 |
| `launcher/` | Windows launcher / startup smoke。 | release approval 或 signed installer。 |
| `docs-site/` | docs site visual check 截圖。 | 文件內容一定正確。 |
| `ui/chatpanel-local-pipeline-chain/` | local ChatPanel 從 Data Interpretation 到 dataset 的 command-chain walkthrough。 | long human desktop local-model session。 |
| `ui/chatpanel-local-training-completion/` | local ChatPanel 訓練、evaluation、visualization、saliency completion walkthrough。 | training quality 或 release approval。 |
| `ui/visualization-render/` | offscreen VisualizationPanel render / blocked-3D evidence。 | interactive Windows 3D acceptance。 |

## 高價值入口

| Artifact | 什麼時候看 |
| --- | --- |
| `quality/latest.md` | 想看最近 fast dashboard。 |
| `ui/human-like-walkthrough/human-like-walkthrough.md` | 想看 UI automated evidence。 |
| `agent_evals/dashboard.md` | 想看 tool-call benchmark。 |
| `mcp/http-walkthrough.md` | 想看 MCP HTTP baseline。 |
| `data_interpretation/format-capability-matrix.md` | 想看 Data Interpretation format boundary。 |
| `data_interpretation/internal-event-preview-backend.png` | 想看 backend internal-event evidence preview 的人眼截圖。 |
| `data_interpretation/internal-event-evidence-A01T-A03T.json` | 想看 A01T/A02T/A03T internal-event evidence payload。 |
| `ui/data-import-wizard-steps/README.md` | 想看目前保留的 Data Import wizard screenshot 入口和 Match Labels placement mode 截圖索引。 |
| `launcher/windows-launcher-walkthrough.md` | 想看 launcher smoke。 |
| `ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.md` | 想看 local ChatPanel tool-chain evidence。 |
| `ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.md` | 想看 local ChatPanel training completion evidence。 |
| `ui/visualization-render/visualization-render-walkthrough.md` | 想看 VisualizationPanel render evidence。 |

## 保留 / 清理規則

保留 current tree 裡的 artifact 時，至少要符合一項：

- canonical docs 或 artifact dashboard 直接引用；
- 代表目前仍要判讀的 product evidence；
- 是 `quality/latest.*`、approved UI baseline candidate、MCP / launcher / Data Import / agent eval
  這類仍在 evidence board 的入口；
- 不是重複截圖，或雖然相似但代表不同使用者流程的重要狀態。

可以清掉的 artifact 類型：

- old goal handoff / continuation notes；這類紀錄應回到 `docs/records/` 或 git history。
- 被更完整 walkthrough supersede 的短版 chatpanel 截圖族群。
- 未被 current docs 引用、可由 script 重跑生成的 dated docs-site visual checkpoint。
- exact duplicate splash / ready screenshots，除非該檔本身是 current artifact family 的入口。
- affected-case / guardrail-only eval 子目錄，當 full deterministic / primary / fallback dashboard
  已涵蓋相同 case 或更完整 suite。
- 舊 Data Interpretation replay screenshots，當 canonical Data Import wizard screenshots 和
  consolidated human-like walkthrough 已覆蓋目前要判讀的畫面。
- exploratory smart-parser / sidebar option screenshots，除非它們被 current product docs 直接引用。

## 最近清理

2026-05-13 current-tree cleanup 已移除：

- `agent_evals/deterministic_changed/`
- `agent_evals/local_*_analysis_tools/`
- `agent_evals/local_*_guardrail_smoke/`
- `ui/chatpanel-local-workflow/`
- `ui/chatpanel-local-training-readiness/`
- `ui/data-source-entry-options/`
- `ui/smart-parser/`
- legacy `ui/data-interpretation-*` replay files

這些檔案不是宣告作廢；它們仍可從 git history 找回。只是 current tree 不再保留
被 full dashboard、canonical wizard screenshots、local pipeline/training walkthrough、
或 consolidated human-like walkthrough 覆蓋的重複 evidence。

2026-05-14 second-pass cleanup removed:

- stale `agent_evals/deterministic/latest.md` that still reported the older 118-case
  deterministic result while root `agent_evals/latest.*` and the dashboard report the
  current 121-case run.
- `ui/training-start-confirmation/`, a short confirmation-dialog replay now covered by
  stronger agent/controller confirmation-boundary evidence and product-smoke claim
  boundaries.
- extra Data Import wizard status variants from the current tree. The retained set is
  one canonical screenshot per wizard step plus four Match Labels placement panels;
  deleted variants remain recoverable from git history or can be regenerated for a
  targeted UX review.

## 新 artifact 要寫清楚

```text
status:
generator:
environment:
supports:
does_not_support:
next_human_or_runtime_gate:
```
