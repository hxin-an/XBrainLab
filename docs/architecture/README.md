# XBrainLab 目前架構

最後更新：`2026-08-13`

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
剩餘距離主要在 compatibility cleanup、refresh exact evidence、human desktop acceptance，以及
product evidence claim boundary。讀本頁時先看下方「目前距離目標多遠」，再進 `ui.md`
的例外地圖；不要從
歷史 checkpoint 數量推論目前架構乾淨度。

## 目前距離目標多遠

| Area | 現況 | 距離目標 |
| --- | --- | --- |
| Backend command spine | `ApplicationService / Command API` 是 product runtime 主入口；`BackendFacade` 已物理移除。同一 Study 的 service instance 共用 command/state lock。 | 還要防止新 wrapper / direct manager mutation 回流。 |
| Assistant boundary | mapped tool exposure 由 backend capability policy 決定；每回合先由 host 將自然語言解析為 immutable scope，單次 tool execution 再交給 coordinator。UI 只讀 worker runtime snapshot，不持有另一份 execution-mode truth。 | 還缺長時間 session、Windows 真人 assistant acceptance 與 frozen benchmark。 |
| UI refresh | Product state-changing render 由 revisioned `ApplicationViewPublication` 連接 backend 與 Qt view；五個 product panels 使用 typed ports，Training progress 另由 narrow transient port 傳遞。Terminal event 在 matching revision 可見前會保留，確認後 exactly-once 投遞。 | Standalone/test constructors 仍保留 controller compatibility；refresh single-truth 仍需 exact-commit source guard 與 product workflow evidence。 |
| BIDS inventory / parsed content | `BidsDatasetIndex` 對一個明確選取的 formal BIDS root 建立 immutable bounded inventory，統一 nested root、subject projection、EEG recordings、events / channels / geometry / JSON sidecars 與 completeness。Small JSON / delimited sidecars 以 complete-bytes SHA-256 + parser/schema identity 進 bounded immutable cache。 | 這不是 pybids replacement、full inheritance 或 BIDS validator；Windows cache hit 仍重新讀完整 bytes，不能用 `ctime` 外推 freshness。 |
| Long-running ownership | `OwnedWorkRegistry` 在 shared command lock 之外配置 operation ID，保存 typed kind / phase、stage、progress、cancel intent 與 terminal receipt。Import、preprocess、epoch、training、evaluation、saliency、render 透過 cooperative checkpoints 或 native runtime stop/cancel 接回同一 owner。 | Source / focused tests 不等於所有 native workers 與真人流程已通過；不可從 cancellable API 推論任何時點都能中斷第三方 native call。 |
| Deferred application work | Training draft resource preview、BIDS montage preparation、Evaluation model summary 與 visualization render 由 application-owned coordinator / worker 處理；generation / request identity 不符的 stale result 不發布。 | 目前只處理 bounded preview / optional montage / detached render，不代表 lazy loading、AutoML 或所有 model architecture 都可 introspect。 |
| Saliency admission | Training terminal path 只發布 metrics；visible `Compute Saliency` 送出明確的 generation/run-bound operation，成功 publication 後才開啟 attribution views。 | 沒有按鈕動作就沒有 saliency 成功主張；Map / Spectrogram source tests 不取代真人 screenshots、scientific validity 或 native 3D acceptance。 |
| Native UI lifecycle | MainWindow 關閉時會先 fence application workers，再以 PyQtGraph 支援的 axis-before-scene 順序關閉 Preprocess plots；取消關閉仍可恢復 plot callbacks。 | Offscreen lifecycle regression 不能取代 Windows / WSLg 長時間互動驗收。 |
| Product evidence | guarded product smokes、real-tools evidence、real GDF full-pipeline smoke 已轉向 command/query truth；product-success tests 也開始阻擋 no-crash / generic panel assertion 形狀。 | lower-level integration tests 仍有 setup/domain 目的的 direct `Study` access，不能全部當 product smoke。 |
| Desktop acceptance | startup、UI baseline、dialog/unit 與 real-data IO 已有 checkpoint evidence。 | Closure branch 尚無 clean exact-commit dashboard PASS；還缺人手 Windows desktop click-through 和長時間 local-model session。 |

## 目前不要誤讀

| 看到的訊號 | 正確解讀 | 不能推論 |
| --- | --- | --- |
| `BackendFacade` 已刪除 | product runtime 不應再從 facade 進 backend。 | Repo 已完全沒有 controller compatibility code。 |
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
| MCP | 無active executable owner；舊adapter provenance只存在Git history。 | 未來恢復必須另開public contract／security decision，不得從history自動復活。 |

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
| Compatibility constructor residue | Product MainWindow 不再注入 controller bundle，但 Training、sidebar 和部分 standalone dialogs 仍保留 compatibility-era parameters/helpers。 | 視為 P2 cleanup；不得讓它們重新成為 product action、readiness 或 render truth。 |
| UI refresh split truth | backend state 正確但畫面顯示舊狀態。 | Product state-changing render 只認 revisioned publication；navigation 與 transient progress 保持非 state-truth，並用 guards 防止 command-result/controller refresh 回流。 |
| deferred terminal delivery | GUI queue 尚未套用 publication 時，training terminal event 若先送出會讓 assistant 留在 Working。 | `ApplicationViewEventPublisher` 保留 revision-bound terminal event；Qt bridge acknowledgement 後重試，只允許 matching revision exactly-once delivery。 |
| `BackendFacade` reintroduction | 這是 guarded regression，不是 current implementation。若 wrapper 回來，就會和 UI / assistant 分裂。 | Architecture guard blocks `BackendFacade` use in product UI / assistant packages and tests. |
| evidence overclaim | dashboard PASS 或 offscreen smoke 被誤解成 product complete。 | Validation docs must keep human desktop acceptance and long local-model sessions as separate claims. |
| weak product tests returning | product-success test 可能退回 no-crash、generic string 或 generic widget assertion。 | Architecture guard now blocks known weak shapes; add new exact-evidence guards only when a real weak pattern appears. |
| Data Interpretation maturity | 資料語意錯會污染後續 training / evidence。 | MVP 先處理代表性 ambiguity，不誇大 final support。 |

## 深入頁面

| File | 用途 |
| --- | --- |
| [backend.md](backend.md) | backend command spine、controllers、legacy removal 詳細現況。 |
| [ui.md](ui.md) | PyQt panels、refresh、observer boundary。 |
| [agent.md](agent.md) | in-app assistant、local-only runtime、tool calls。 |
| [data_pipeline.md](data_pipeline.md) | EEG import / preprocess / dataset / training pipeline。 |
| [Validation](../validation/README.md) | 測試層級、artifact identity 與 evidence 邊界。 |
