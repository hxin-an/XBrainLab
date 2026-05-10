# XBrainLab 目前狀態

最後更新：`2026-05-09`

這頁只回答一件事：**現在能相信什麼，還不能宣稱什麼，下一步該做什麼。**
完整階段安排看 [Roadmap](planning/roadmap.md)，下一輪施工看 [Now](planning/now.md)。

## 一句話

XBrainLab 正在收斂成 Windows 本地 EEG / BCI 桌面工具。主線已經從「到處補功能」
改成「先讓 backend、UI、assistant、MCP 共用同一套 workflow truth」。

目前不能宣稱 product complete。

## 現況總覽

| 區域 | 目前狀態 | 邊界 |
| --- | --- | --- |
| Backend | `ApplicationService / Command API` 已是主要 command spine。 | Phase 1A 還要清 product legacy path、UI refresh path 和測試裡的舊成功路徑。 |
| UI | PyQt 主流程、Data Interpretation wizard、training / evaluation / visualization surface 都有 baseline。 | automated walkthrough 不等於 human Windows desktop acceptance。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 已存在。 | 還不是 final import system；複雜 label / trigger / XDF / LSL 還不能誇大。 |
| Agent / MCP | tool surface 和 MCP adapter 已開始走同一套 command / capability / state snapshot。 | 這是 product baseline，不是完整 thesis benchmark 或 MCP client certification。 |
| Packaging | Windows launcher / startup smoke 有 evidence。 | 還不是 signed installer，也不是 release approval。 |

## 下一個真正 blocker

**Phase 1A：Backend Command Spine Cleanup。**

這不是為了架構漂亮，而是為了避免 MVP 前繼續累積 bug：

- product runtime 不應偷偷 fallback 到 legacy controller mutation。
- UI refresh 不應每個頁面自己猜狀態。
- 測試不應把舊 fallback 當作成功條件。
- `BackendFacade` 只能當 assistant / script 的便利入口，不能成為第二套 backend。

## 可以宣稱

- Roadmap 目前主線合理：backend cleanup -> Data Interpretation MVP -> tool-call baseline -> Windows desktop acceptance。
- `ApplicationService / Command API` 是目前要收斂的 product spine。
- Data Interpretation 和 tool-call baseline 都屬於 MVP，不應被推到後期。
- 現有 artifacts 能作為工程 evidence，但每個 evidence 都有明確邊界。

## 不能宣稱

- product complete。
- backend target architecture fully aligned。
- Data Interpretation final。
- automated UI walkthrough 等於 human Windows desktop acceptance。
- tool-call eval 等於 UI / product completion。
- MCP baseline 等於完整 external-agent certification。
- launcher smoke 等於 release approval 或 signed installer。

## 最近驗證

| Gate | 最近結果 | 用途 |
| --- | --- | --- |
| `mkdocs build --strict` | PASS | 文件站可建。 |
| `git diff --check` | PASS | diff 格式乾淨。 |
| backend / agent / MCP focused tests | 最近曾通過 targeted suites。 | 支撐 command spine / tool surface baseline，不取代產品驗收。 |
| GitHub PR checks | 最近 head 曾全綠。 | 支撐 branch 可 review，不等於產品完成。 |

## 先看哪裡

| 你想知道 | 讀這裡 |
| --- | --- |
| 下一步施工 | [planning/now.md](planning/now.md) |
| 產品階段 | [planning/roadmap.md](planning/roadmap.md) |
| 目前架構 | [architecture/README.md](architecture/README.md) |
| 目標架構 | [target/architecture.md](target/architecture.md) |
| 證據怎麼解讀 | [validation/README.md](validation/README.md) |
