# XBrainLab 目前狀態

最後更新：`2026-05-14`

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
| UI | PyQt 主流程、Data Interpretation wizard、training / evaluation / visualization surface 都有 baseline。Epoch command-backed UI path now has a real-GDF offscreen smoke for A01T/A02T/A03T and a BIDS-EEG import handoff smoke; product command success no longer opens a blocking success modal. | automated walkthrough/offscreen smoke 不等於 human Windows desktop acceptance。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 已存在；current UX checkpoint includes canonical wizard screenshots, internal EEG label evidence, loaded-label placement evidence for EEG event order / label time / label interval / label event code, BIDS-EEG `events.tsv` / `events.json` review, blocked conversion fallback, beginner Review and Import evidence, and backend-generated epoch handoff evidence. | 支援的是 XBrainLab BIDS-EEG import path，不是 all-modality full BIDS validator；P300/ERP hierarchy、SSVEP/c-VEP semantics、clinical long recordings、XDF/LSL、OpenBCI/BrainFlow、MOABB adapters、proprietary logs、nested unknown MAT schemas、pickle、user Python converters 都不能誇大。 |
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
| Test truth | product-success tests 已開始被 guard 約束，不能用 facade、legacy fallback、direct mutable `Study` state、positive controller lookup、no-crash 字串當成功證據；MCP product status/progress path 也被 guard 禁止直接讀 mutable `Study` state 或直接呼叫 `Study` controller/generator methods。 |
| Docs truth | current truth 已同步到 canonical docs；最大文件風險是可讀性，不是缺少歷史紀錄。 |

## 目前分數

這是 engineering scorecard，不是 release approval。分數回答「離目前 target architecture 還差多遠」。

| Area | Score | 距離 10 分 | 為什麼還不是 10 |
| --- | ---: | ---: | --- |
| Backend architecture | 8.6 / 10 | 1.4 | command spine、focused services、facade removal 已落地；仍要防 direct manager mutation / wrapper 回流，且部分 product evidence 還依賴 lower-level setup。 |
| UI refresh truth | 7.4 / 10 | 2.6 | high-value actions 和主要 refresh 已走 command/query/coordinator；panel bootstrap、observer bridge、readonly display fallback 還保留 controller adapters。 |
| Test / product evidence | 8.3 / 10 | 1.7 | exact-evidence stack 已取代多個 generic non-empty / no-crash tests；仍有 mock-heavy UI tests、lower-level direct `Study` setup，以及 human acceptance gap。 |
| Docs correctness | 8.6 / 10 | 1.4 | current / architecture / validation claim boundaries 已同步；仍需隨 UX branch 和 human evidence 更新。 |
| Docs completeness | 8.2 / 10 | 1.8 | 主要入口、validation、artifact governance 都有；仍缺完整人工 Windows acceptance record 和 release packaging evidence。 |
| Docs readability | 8.0 / 10 | 2.0 | 入口摘要與 backend quick-read 已改善；validation history 仍長，後續要繼續把 checkpoint 索引和 current truth 分開。 |

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
| Fast quality dashboard | 2026-05-14 00:11:43 UTC+08:00 `PASS`。 | 最新 branch engineering health：ruff、basedpyright、architecture、startup、UI baseline/dialog/unit、real-data IO。不是 release approval。 |
| Architecture compliance | `Architecture compliant!`，guard unit `91 passed`。 | 阻擋 `BackendFacade`、legacy fallback、direct mutable `Study` state、positive controller lookup、docs overclaim 等已知 regression。 |
| Exact-evidence stack | 2026-05-13 focused backend / real-data / real-tools / UI walkthrough suites PASS。 | A01T、A01T/A02T/A03T GDF+MAT、public EDF/GDF/SET/CNT、ApplicationService synthetic workflow、real-tool chain、UI product walkthrough 都已從 generic non-empty evidence 收斂到 command/query state、exact event/epoch/split/history assertions。 |
| UI refresh / controller binding | 2026-05-13 focused UI refresh / integration / panel binding suites PASS。 | MainWindow launch/navigation/tab refresh 和 injected controller event wiring 不再用 positive legacy lookup 當成功證據；仍不代表 full controller removal。 |
| Data Interpretation label semantics | 2026-05-14 focused backend unit suites `144 passed`；combined focused UI/replay/product smoke `277 passed`。 | 支撐 reviewed target EEG event selection、event-code label files、interval end/stop/offset duration、run-dependent internal event mapping、BIDS-EEG selected scope/sidecars/recipe/state snapshot preservation、epoch handoff 的 backend contract；不是 human Data Import acceptance。 |
| Data Import screenshots | `artifacts/ui/data-import-wizard-steps/` 保留 canonical wizard screenshots、conversion fallback/example、BIDS-EEG events、Review and Import 三狀態、BIDS ready state、Epoch after BIDS import，以及四個 loaded-label placement panels。 | 支撐目前畫面判讀；不是 human Windows click-through acceptance，也不是所有非目標格式的支援聲明。 |
| Docs / artifact truth | `mkdocs build --strict`、`git diff --check`、artifact current-tree cleanup PASS checkpoints。 | 文件站可建、入口更可讀、current tree 減少重複 artifact；不代表文件內容能取代 runtime evidence。 |
| GitHub PR checks | 最近 head 曾全綠。 | 支撐 branch 可 review，不等於產品完成。 |

## 先看哪裡

| 你想知道 | 讀這裡 |
| --- | --- |
| 下一步施工 | [planning/now.md](planning/now.md) |
| 產品階段 | [planning/roadmap.md](planning/roadmap.md) |
| 目前架構 | [architecture/README.md](architecture/README.md) |
| 目標架構 | [target/architecture.md](target/architecture.md) |
| 證據怎麼解讀 | [validation/README.md](validation/README.md) |
