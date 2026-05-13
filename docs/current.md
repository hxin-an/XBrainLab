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
| Agent / MCP | tool surface 和 MCP adapter 已開始走同一套 command / capability / state snapshot；real `Study` 的 assistant pipeline stage 也改為只信 ApplicationService snapshot，snapshot 不可用時 fail closed，不再退回 mutable `Study` 欄位推斷；HTTP MCP job progress message 也由 ApplicationService training state 提供，不再讀 `service.study.trainer`。 | mock / legacy compatibility 還有明確 fallback；這是 product baseline，不是完整 thesis benchmark 或 MCP client certification。 |
| Packaging | Windows launcher / startup smoke 有 evidence。 | 還不是 signed installer，也不是 release approval。 |

## Phase 1A 收尾焦點

現在的 blocker 不是單一 bug，而是把 **UI refresh / backend command truth / test evidence**
收斂到可以交接的程度。讀這段時先看結論，再看下面的剩餘例外表。

| 判斷 | 現況 |
| --- | --- |
| Backend spine | `ApplicationService / Command API` 是 product runtime 入口；`BackendFacade` 已移除，不是可用 backend layer。 |
| UI action truth | Dataset、Preprocess、Training、Evaluation、Visualization 的高價值 action 已優先走 service command 或 typed readonly command。 |
| UI refresh truth | navigation、observer、command-result refresh 已集中到 refresh coordinator；部分 panel render/detail path 還保留 controller adapter。 |
| Test truth | product-success tests 已開始被 guard 約束，不能用 facade、legacy fallback、direct mutable `Study` state、positive controller lookup、no-crash 字串當成功證據。 |
| Docs truth | current truth 已同步到 canonical docs；最大文件風險是可讀性，不是缺少歷史紀錄。 |

## 剩餘 legacy / refresh 例外地圖

| 類型 | 目前在哪裡 | 為什麼還在 | 下一步 |
| --- | --- | --- | --- |
| Observer bridge adapter | `MainWindow` panel bootstrap、`BasePanel` / `QtObserverBridge` wiring | panels 仍需要 controller `Observable` events 驅動 UI refresh。 | 後續若要 full zero-controller UI，需要新的 UI-facing event/state API，不是直接刪 controller。 |
| Human-in-loop UI request | montage picker / matching、label import target choice、dialog-local validation | 這些是使用者互動與 dialog orchestration，不完全是 backend command。 | 保留 UI request 邊界；只把 confirmed action 送進 command。 |
| Mock / legacy compatibility | `run_legacy_controller_fallback()`、`get_legacy_controller_from_study()`、panel constructor fallback tests | 舊 unit tests、非 real-`Study` callers、isolated widget tests 還依賴 controller-shaped doubles。 | 繼續用 guard 限制它們不能成為 product-success evidence。 |
| Lower-level pipeline tests | 少數 integration pipeline tests 仍直接 setup/read `Study` fields；real GDF full-pipeline smoke 已轉成 ApplicationService command/query evidence 並納入 guard。 | 剩餘 direct `Study` cases 多半是 domain / fixture setup，不是 UI product smoke。 | 繼續逐條分類；只有先補 command/query replacement 的 suite 才擴大 product-evidence guard。 |
| Human desktop acceptance | Windows launcher、長時間本地模型、人工 click-through | automated smoke 不能代表人手驗收。 | MVP 前要補人工紀錄與可重跑 artifact。 |

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
| ApplicationService workflow query truth | 2026-05-13 focused backend workflow / architecture guard PASS。 | 支撐 `test_application_service_workflow.py` 不再用 direct `service.study.get_datasets_generator()` 作為 product evidence；不等於所有 lower-level integration tests 都已改寫。 |
| training command/query state truth | 2026-05-13 focused training integration / UI panel regression / domain unit / architecture guard PASS。 | 支撐 `test_training_integration.py` 與 `test_e2e_training.py` 的 UI-facing training config evidence 改由 `ConfigureTrainingCommand` / `QueryStateCommand` state 驗證；`Study.training_option` 只保留在 unit-level domain compatibility tests。 |
| real-data pipeline command spine | 2026-05-13 focused real GDF pipeline / architecture guard PASS。 | 支撐 `test_real_data_pipeline.py` 的 load -> preprocess -> epoch -> dataset -> train smoke 改用 `ApplicationService` commands、`QueryStateCommand` state / training history、split audit，而不是 direct mutable `Study` success truth。 |
| preprocess validation command-load setup | 2026-05-13 focused preprocess validation / architecture guard PASS。 | 支撐 `test_preprocess_validation.py` 的 synthetic FIF fixture load 成功證據改由 `LoadDataCommand` / `QueryStateCommand` state 驗證；preprocess edge-case assertions 仍是 controller-level regression，不被誇大成完整 product smoke。 |
| preprocess controller test-quality cleanup | 2026-05-13 focused PreprocessController integration PASS。 | 支撐 `test_preprocess_controller.py` 的 real GDF controller regressions 不再用 controller import 作為 fixture load path，且 event/history assertions 比 generic non-empty 更具體；仍不是 product UI acceptance。 |
| evaluation display command evidence | 2026-05-13 focused EvaluationPanel unit / lint / type / architecture PASS。 | 支撐 Evaluation panel 在 service-owned average metrics 缺失時會清空 stale run metrics，且不 fallback 到 stale controller pooled metrics；不等於完整 human evaluation UX acceptance。 |
| MCP HTTP progress command-state truth | 2026-05-13 focused MCP HTTP / state-service / architecture PASS。 | 支撐 HTTP MCP job progress message 由 ApplicationService training state snapshot 提供，不再直接讀 `service.study.trainer`。 |
| LLM pipeline stage command truth | 2026-05-13 focused pipeline-state / agent context / architecture guard PASS。 | 支撐 real `Study` assistant stage 不再於 ApplicationService snapshot failure 時 fallback 到 direct mutable `Study` state；不等於 tool-call benchmark accuracy。 |
| docs current-truth overclaim guard | 2026-05-13 focused architecture guard PASS。 | 支撐 current/architecture/validation/now/index 不應把 product complete、full zero-controller UI、human acceptance、release approval 寫成已完成事實。 |
| UI integration controller evidence | 2026-05-13 focused UI integration / UI refresh / panel binding suites PASS。 | 支撐 UI integration baseline 不再 positive assert legacy `Study.get_controller()` resolution；不等於 full zero-controller UI。 |
| UI controller fallback helper-scope | 2026-05-12 targeted PASS。 | 支撐 product UI method 不再直接呼叫 legacy fallback helper；不代表所有 read-only controller wiring 已移除。 |
| Epoch UI real-GDF smoke | 2026-05-12 targeted PASS。 | 支撐 reported A01T/A02T/A03T Epoch UI freeze regression，不等於完整 Windows human acceptance。 |
| docs readability checkpoint | 2026-05-13 targeted docs / architecture / UI product gates PASS。 | 支撐 current/architecture/validation 入口可讀性整理沒有破壞現有 guard 或 UI smoke；不代表產品完成。 |
| quality dashboard | 2026-05-13 21:51:50 UTC+08:00 `fast` PASS。 | engineering health，不是 release approval。 |
| GitHub PR checks | 最近 head 曾全綠。 | 支撐 branch 可 review，不等於產品完成。 |

## 先看哪裡

| 你想知道 | 讀這裡 |
| --- | --- |
| 下一步施工 | [planning/now.md](planning/now.md) |
| 產品階段 | [planning/roadmap.md](planning/roadmap.md) |
| 目前架構 | [architecture/README.md](architecture/README.md) |
| 目標架構 | [target/architecture.md](target/architecture.md) |
| 證據怎麼解讀 | [validation/README.md](validation/README.md) |
