# XBrainLab Artifacts

最後更新：`2026-05-13`

`artifacts/` 放的是機器產物：dashboard、截圖、walkthrough、eval output、packaging evidence。
它們是 evidence，不是 current truth。

目前真相請看 `docs/current.md`；evidence 怎麼解讀請看 `docs/validation/README.md`。

## 使用規則

- artifact 可以支撐它實際跑過的範圍。
- artifact 不能自動擴張成 product complete、human acceptance 或 thesis claim。
- 不手改 generated artifact 來讓結果看起來更好。
- 如果 artifact 和 current docs 衝突，先查 source / runtime，再更新 canonical docs 或重跑 artifact。

## 主要 artifact family

| Family | 用途 | 不能代表 |
| --- | --- | --- |
| `quality/` | fast engineering dashboard。 | product complete。 |
| `ui/human-like-walkthrough/` | automated PyQt walkthrough、截圖、按鈕狀態。 | human Windows desktop acceptance。 |
| `agent_evals/` | tool-call benchmark / scorer output。 | UI usability 或 EEG training quality。 |
| `mcp/` | MCP stdio / HTTP adapter walkthrough。 | 完整 MCP client certification。 |
| `data_interpretation/` | format capability matrix、internal-event preview evidence。 | 所有 EEG 格式完整支援，或數字 event code 的真實 class semantics。 |
| `ui/data-import-wizard-steps/` | Data Import wizard review screenshots。 | final Match Labels / Review and Import UX，或 human Windows acceptance。 |
| `launcher/` | Windows launcher / startup smoke。 | release approval 或 signed installer。 |
| `docs-site/` | docs site visual check 截圖。 | 文件內容一定正確。 |

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
| `ui/data-import-wizard-steps/README.md` | 想看目前 Data Import wizard 和 Match Labels placement mode 截圖索引。 |
| `launcher/windows-launcher-walkthrough.md` | 想看 launcher smoke。 |

## 新 artifact 要寫清楚

```text
status:
generator:
environment:
supports:
does_not_support:
next_human_or_runtime_gate:
```
