# XBrainLab 目前架構

最後更新：`2026-07-10`

這裡描述目前實作，不描述理想終局。目標態請看 [target/architecture.md](../target/architecture.md)。

## 一句話

XBrainLab 正在把 UI、assistant、scripts 收斂到同一個 backend command surface：

```text
UI / assistant / scripts
  -> ApplicationService / Command API
  -> focused command services
  -> Study / DataManager / TrainingManager
```

這個方向已經有實作基礎。Backend command spine 和 `BackendFacade` removal 已經落地；
剩餘距離主要在 UI controller adapter、human desktop acceptance、以及 product evidence
claim boundary。讀本頁時先看下方「目前距離目標多遠」，再進 `ui.md` 的例外地圖；不要從
歷史 checkpoint 數量推論目前架構乾淨度。

## 目前距離目標多遠

| Area | 現況 | 距離目標 |
| --- | --- | --- |
| Backend command spine | `ApplicationService / Command API` 是 product runtime 主入口；`BackendFacade` 已物理移除。同一 Study 的 service instance 共用 command/state lock。 | 還要防止新 wrapper / direct manager mutation 回流。 |
| Assistant boundary | mapped tool exposure 由 backend capability policy 決定；單次 tool execution 有 coordinator，UI 只讀 worker runtime snapshot。 | 還缺 approved local-model cache、長時間 session 與 Windows 真人 assistant acceptance。 |
| UI refresh | command-result、navigation、known observer event 已集中到 refresh coordinator。 | panel constructor / observer bridge 還依賴 injected controllers，不是 full zero-controller UI。 |
| Product evidence | guarded product smokes、real-tools evidence、real GDF full-pipeline smoke 已轉向 command/query truth；product-success tests 也開始阻擋 no-crash / generic panel assertion 形狀。 | lower-level integration tests 仍有 setup/domain 目的的 direct `Study` access，不能全部當 product smoke。 |
| Desktop acceptance | startup、UI baseline、dialog/unit、real-data IO dashboard PASS。 | 還缺人手 Windows desktop click-through 和長時間 local-model session。 |

## 目前不要誤讀

| 看到的訊號 | 正確解讀 | 不能推論 |
| --- | --- | --- |
| `BackendFacade` 已刪除 | product runtime 不應再從 facade 進 backend。 | UI 已 full zero-controller。 |
| `ApplicationService` tests / smokes 綠 | command spine 和 state/query truth 有保護。 | 每個 panel display path 都已完全不讀 controller。 |
| product-success weak evidence guard 綠 | facade、legacy fallback、direct `Study` state、controller lookup、no-crash / generic panel assertion 等回歸會被擋。 | 所有 mock-heavy 或 lower-level tests 都已重寫。 |
| artifacts current tree 已 prune | current evidence 入口比較少、比較好讀。 | screenshot freshness 或 human Windows acceptance 已完成。 |
| automated walkthrough / dashboard PASS | 可支撐 engineering health 和 offscreen product evidence。 | 可取代人手 Windows launcher / Data Import / local model click-through。 |

## 目前分層

| Layer | 現在負責 | 目前風險 |
| --- | --- | --- |
| PyQt UI | 使用者 workflow、dialogs、visible state、page refresh。 | 還要避免各頁自己維護第二份 workflow truth。 |
| `ApplicationService` | command dispatch、capability / confirmation gate、result envelope。 | 必須保持 spine，不要變成 god object。 |
| focused services | Data Interpretation、preprocess、dataset、training、analysis、lifecycle。 | 邊界要靠 tests 和 architecture guard 維持。 |
| `Study` / managers | domain state、data lifecycle、training lifecycle。 | product path 不應直接繞過 command spine；lower-level domain tests 仍可 setup state。 |
| assistant / scripts | tool / JSON payload 轉 command；real `Study` pipeline stage 來自 ApplicationService state snapshot。 | assistant baseline 要等 current truth、verification boundary 和 UI product path 重新穩定。 |
| MCP | 既有 adapter code / tests / artifacts 是歷史探索或相容性證據。 | 已從 active roadmap 移除；不再作為產品架構目標、handoff gate 或 thesis evidence 前置。 |

## Roadmap 對應

| Roadmap | 架構含義 |
| --- | --- |
| Rebaseline | 讓 branch/worktree、known blockers、validation claim 和 canonical docs 對齊。 |
| Desktop MVP | 清 product legacy path、UI refresh truth、test adapter truth，並讓 Data Interpretation 到 visualization 的桌面 workflow 可跑。 |
| Product Polish / Release Candidate | 統一 UI visual language、empty/loading/error state、artifact freshness 和 troubleshooting。 |
| Assistant MVP | 讓 in-app assistant 走相同 command / capability / state snapshot。 |
| Thesis Evidence | 在產品主線穩定後建立 tool-call / agent benchmark evidence。 |

## Active Risks

| Risk | 為什麼重要 | 處理方向 |
| --- | --- | --- |
| controller adapter remains | UI still needs injected controllers for panel constructors and observer bridges. | Treat these as adapter / observer boundary; do not use them as action, readiness, or product-success truth. |
| UI refresh split truth | backend state 正確但畫面顯示舊狀態。 | command result / changed state 驅動 refresh；command 執行期間的 observer refresh 會被暫停，避免先用 stale controller state 重刷。 |
| `BackendFacade` reintroduction | 這是 guarded regression，不是 current implementation。若 wrapper 回來，就會和 UI / assistant 分裂。 | Architecture guard blocks `BackendFacade` use in product UI / assistant packages and tests. |
| evidence overclaim | dashboard PASS 或 offscreen smoke 被誤解成 product complete。 | Validation docs must keep human desktop acceptance and long local-model sessions as separate claims. |
| weak product tests returning | product-success test 可能退回 no-crash、generic string 或 generic widget assertion。 | Architecture guard now blocks known weak shapes; add new exact-evidence guards only when a real weak pattern appears. |
| Data Interpretation maturity | 資料語意錯會污染後續 training / evidence。 | MVP 先處理代表性 ambiguity，不誇大 final support。 |
| MCP overhang | 歷史 MCP docs / artifacts 容易讓人誤以為它仍是 roadmap。 | Current / roadmap / validation docs 明確標示 MCP 已退出 active plan；records 保留歷史即可。 |

## 深入頁面

| File | 用途 |
| --- | --- |
| [backend.md](backend.md) | backend command spine、controllers、legacy removal 詳細現況。 |
| [ui.md](ui.md) | PyQt panels、refresh、observer boundary。 |
| [agent.md](agent.md) | in-app assistant、local-only runtime、tool calls。 |
| [data_pipeline.md](data_pipeline.md) | EEG import / preprocess / dataset / training pipeline。 |
| [validation.md](validation.md) | 測試層級與 evidence 邊界。 |
