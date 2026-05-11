# XBrainLab 目前架構

最後更新：`2026-05-09`

這裡描述目前實作，不描述理想終局。目標態請看 [target/architecture.md](../target/architecture.md)。

## 一句話

XBrainLab 正在把 UI、assistant、MCP、scripts 收斂到同一個 backend command surface：

```text
UI / assistant / MCP / scripts
  -> ApplicationService / Command API
  -> focused command services
  -> Study / DataManager / TrainingManager
```

這個方向已經有實作基礎，但還沒有完全收乾淨。

## 目前分層

| Layer | 現在負責 | 目前風險 |
| --- | --- | --- |
| PyQt UI | 使用者 workflow、dialogs、visible state、page refresh。 | 還要避免各頁自己維護第二份 workflow truth。 |
| `ApplicationService` | command dispatch、capability / confirmation gate、result envelope。 | 必須保持 spine，不要變成 god object。 |
| focused services | Data Interpretation、preprocess、dataset、training、analysis、lifecycle。 | 邊界要靠 tests 和 architecture guard 維持。 |
| `Study` / managers | domain state、data lifecycle、training lifecycle。 | legacy controller mutation path 還要在 product runtime 清乾淨。 |
| `BackendFacade` | Legacy compatibility wrapper outside product runtime. | Product UI / assistant / MCP / current headless scripts should use `ApplicationService / Command API` directly. |
| assistant / MCP | tool / JSON payload 轉 command。 | MVP 先做 baseline；client certification 屬 Phase 4。 |

## Roadmap 對應

| Roadmap | 架構含義 |
| --- | --- |
| Phase 1A | 清 product legacy path、UI refresh truth、test adapter truth。 |
| Phase 1B | 讓 Data Interpretation 成為正式資料入口。 |
| Phase 1C | 讓 assistant / MCP 走相同 command / capability / state snapshot。 |
| Phase 1D | 用人手 Windows workflow 驗證整條產品線。 |

## Active Risks

| Risk | 為什麼重要 | 處理方向 |
| --- | --- | --- |
| legacy controller path | 桌面操作可能繞過 command spine，測試也可能保護舊路徑。 | real `Study` product path 不再 hidden fallback。 |
| UI refresh split truth | backend state 正確但畫面顯示舊狀態。 | command result / changed state 驅動 refresh。 |
| `BackendFacade` scope creep | wrapper 若回到 product runtime，就會和 UI / MCP 分裂。 | Architecture guard blocks `BackendFacade` use in product UI / assistant / MCP packages. |
| Data Interpretation maturity | 資料語意錯會污染後續 training / evidence。 | MVP 先處理代表性 ambiguity，不誇大 final support。 |
| MCP session confusion | headless session 容易被誤解成桌面 UI 控制。 | Phase 4 明確 session ownership 和 client matrix。 |

## 深入頁面

| File | 用途 |
| --- | --- |
| [backend.md](backend.md) | backend command spine、controllers、facade 詳細現況。 |
| [ui.md](ui.md) | PyQt panels、refresh、observer boundary。 |
| [agent.md](agent.md) | in-app assistant、local-only runtime、tool calls。 |
| [data_pipeline.md](data_pipeline.md) | EEG import / preprocess / dataset / training pipeline。 |
| [validation.md](validation.md) | 測試層級與 evidence 邊界。 |
