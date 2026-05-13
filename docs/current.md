# XBrainLab 目前狀態

最後更新：`2026-05-13`

這頁只回答一件事：**現在能相信什麼，還不能宣稱什麼，下一步該做什麼。**
完整階段安排看 [Roadmap](planning/roadmap.md)，下一輪施工看 [Now](planning/now.md)。

## 一句話

XBrainLab 正在收斂成 Windows 本地 EEG / BCI 桌面工具。主線已經從「到處補功能」
改成「先讓 backend、UI、assistant、MCP 共用同一套 workflow truth」。

目前不能宣稱 product complete。

## 現況總覽

| 區域 | 目前狀態 | 邊界 |
| --- | --- | --- |
| Backend | `ApplicationService / Command API` 已是主要 command spine；UI / assistant / MCP / current headless product runtime 不再把 `BackendFacade` 當入口，product-success tests 也改用 command evidence；`BackendFacade` module 已物理移除；UI product methods 不能直接呼叫 `run_legacy_controller_fallback()`，fallback 必須隔離在 explicit legacy/helper boundary；MainWindow panel bootstrap controller lookup 也已收進 named legacy quarantine helper，不再有 `main_window.py` guard 例外。 | controller fallback 仍保留為 mock / legacy compatibility；panels 仍接受 injected controllers 作為 observer / legacy adapter，不等於 full zero-controller UI；不代表 human Windows desktop acceptance。 |
| UI | PyQt 主流程、Data Interpretation wizard、training / evaluation / visualization surface 都有 baseline。Epoch command-backed UI path now has a real-GDF offscreen smoke for A01T/A02T/A03T and no longer opens a blocking success modal after product command success. | automated walkthrough/offscreen smoke 不等於 human Windows desktop acceptance。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 已存在；current UX checkpoint includes mainstream Match Labels placement evidence for EEG event order, label time, label interval, and label event code. | 還不是 final import system；複雜 label / trigger / XDF / LSL 還不能誇大，也不是 final Match Labels / Review and Import UX。 |
| Agent / MCP | tool surface 和 MCP adapter 已開始走同一套 command / capability / state snapshot。 | 這是 product baseline，不是完整 thesis benchmark 或 MCP client certification。 |
| Packaging | Windows launcher / startup smoke 有 evidence。 | 還不是 signed installer，也不是 release approval。 |

## 下一個真正 blocker

**Phase 1A 收尾：Backend command spine validation + product smoke gap。**

這不是為了架構漂亮，而是為了避免 MVP 前繼續累積 bug：

- product runtime 不應偷偷 fallback 到 legacy controller mutation。
- UI refresh 不應每個頁面自己猜狀態。
- 測試不應把舊 fallback 當作成功條件。
- `BackendFacade` 已物理移除；product runtime、agent、MCP、headless scripts 要直接使用
  `ApplicationService / Command API` 或薄 command adapter。
- Dataset split / generation 的預設 UI config 已改成可訓練 trial splits，並有
  `ApplicationService` regression 證明下游 training readiness。
- Epoch UI freeze/hang reality gap 已補：real-GDF offscreen smoke 證明 A01T/A02T/A03T
  product command epoching 回到 UI、不開 blocking success modal；preprocess preview 在 epoched
  state 會取消 queued plot timer，避免 locked state 後又嘗試畫 epochs。
- 最新 backend hardening 又補上 command-time observer refresh suppression、read-only command
  state preservation、unsupported command structured failure result，以及 product walkthrough
  對 `TrainCommand` confirmation / `append` / `interactive` contract 的測試對齊。
- 最新 UI controller fallback helper-scope cleanup 補上 architecture guard：product UI methods
  不能直接呼叫 `run_legacy_controller_fallback()`；dataset / preprocess / training /
  visualization / AgentManager / TrainingSettingDialog 的 fallback branches 已收進 `_legacy_*`
  helpers，mock / legacy `None` adapter 情境才會執行 controller fallback。
- 最新 real-tools evidence cleanup 把 LLM real-tool integration tests 從 direct controller reads /
  generic no-crash checks 改成查 `QueryStateCommand` diagnostics、command-visible side effects
  和 synchronous non-interactive `TrainCommand` 結果；UI product walkthrough 的 dry-run training
  也改為 patch ApplicationService training command handler，不再 patch `TrainingController`
  當成功證據。
- 最新 product-smoke evidence cleanup 把 `test_product_walkthrough.py`、`test_epoch_runtime.py`、
  `test_real_tools_e2e.py` 和 real-tools integration suites 的 success assertions 從 direct
  mutable `Study` state read 改成 `QueryStateCommand` / UI-visible state；architecture guard 也
  新增 guarded product-smoke direct Study-state rule，避免 product-success tests 重新用
  `study.epoch_data`、`study.datasets`、`study.model_holder` 或 `study.get_datasets_generator()`
  當成功證據。

## 可以宣稱

- Roadmap 目前主線合理：backend cleanup -> Data Interpretation MVP -> tool-call baseline -> Windows desktop acceptance。
- `ApplicationService / Command API` 是目前要收斂的 product spine。
- `BackendFacade` 不再是可用 backend layer；舊 facade API coverage 已由 command/service/helper tests 取代。
- Data Interpretation 和 tool-call baseline 都屬於 MVP，不應被推到後期。
- 現有 artifacts 能作為工程 evidence，但每個 evidence 都有明確邊界。

## 不能宣稱

- product complete。
- full product target architecture across later phases。
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
| backend / agent / MCP focused tests | 2026-05-12 targeted suites PASS。 | 支撐 command spine / tool surface baseline，不取代產品驗收。 |
| Data Import runtime integration | 2026-05-13 targeted ApplicationService / agent-MCP / UI command-refresh suites PASS。 | 支撐 current runtime integration branch，不等於 human Windows desktop acceptance。 |
| real-tools command evidence | 2026-05-13 focused real-tools / product walkthrough suites PASS。 | 支撐 LLM real tools 和 UI product smoke 使用 command/state truth，不等於完整 human desktop acceptance 或 training quality。 |
| product-smoke query truth | 2026-05-13 focused product walkthrough / epoch runtime / real-tools UI E2E / real-tools suites PASS。 | 支撐 guarded product smokes 不再以 mutable `Study` state read 當成功證據；不等於 full zero-controller UI 或 human desktop acceptance。 |
| UI controller fallback helper-scope | 2026-05-12 targeted PASS。 | 支撐 product UI method 不再直接呼叫 legacy fallback helper；不代表所有 read-only controller wiring 已移除。 |
| Epoch UI real-GDF smoke | 2026-05-12 targeted PASS。 | 支撐 reported A01T/A02T/A03T Epoch UI freeze regression，不等於完整 Windows human acceptance。 |
| quality dashboard | 2026-05-13 13:52:36 UTC+08:00 `fast` PASS。 | engineering health，不是 release approval。 |
| GitHub PR checks | 最近 head 曾全綠。 | 支撐 branch 可 review，不等於產品完成。 |

## 先看哪裡

| 你想知道 | 讀這裡 |
| --- | --- |
| 下一步施工 | [planning/now.md](planning/now.md) |
| 產品階段 | [planning/roadmap.md](planning/roadmap.md) |
| 目前架構 | [architecture/README.md](architecture/README.md) |
| 目標架構 | [target/architecture.md](target/architecture.md) |
| 證據怎麼解讀 | [validation/README.md](validation/README.md) |
