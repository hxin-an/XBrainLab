# XBrainLab Decisions

最後更新：`2026-05-04`

## 這份文件的用途

這份文件是目前有效決策的濃縮入口。

舊 ADR 的核心內容已整合到這裡，原 legacy ADR 文件已刪除。這份文件會標記：

- 目前有效決策
- 歷史決策
- 需要重新驗證的決策
- 被新方向取代的早期想法

## 目前有效決策

| 決策 | 狀態 | 說明 |
| --- | --- | --- |
| 穩定化優先 | active | 先讓既有 app 可跑、可測、可理解，再做 agent redesign。 |
| app 內 assistant 是 workflow operator | active | 它不是外部 coding assistant，也不是普通聊天視窗。 |
| assistant runtime local-only | active | 為了簡化開發、部署、隱私和驗證，assistant product runtime 已 local-only；remote backend modules 已從 product package 移除，`openai` / `google-genai` 只留 optional `legacy-remote-llm` dependency group。 |
| tool surface 可重設計 | active | 不被舊工具 taxonomy 綁住，應以 workflow intent 設計。 |
| validation 是 thesis-critical | active | 測試和 evidence 是論文主張的一部分。 |
| 文件要少數 canonical 化 | active | 短期 AI / agent 文件整合後刪除，只保留少數 canonical 文件。 |
| product delivery milestone 是最低門檻 | active | 目前已進入 product-delivery engineering；milestone 不是工作上限，agent 應把程式做到可用、可維護、可驗證。 |
| tool-call eval 等產品主線穩定後再做 | active | Eval / thesis evidence 應測穩定產品主線，不應太早測半成品 bug。 |
| local LLM 下載需受容量邊界控制 | active | 可下載模型，但單模型原則 10GB 內、總 cache 原則 20GB 內；27B+ 需使用者明確同意。 |
| local LLM 不使用中國模型 | active | 不使用中國公司或中國來源模型；Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 等不列入 primary / fallback 選型。 |
| 資料匯入目標是 Data Interpretation System | active | 使用者提供資料位置後，系統應建立可預覽、可驗證、可重跑的資料解讀；不以單純 load file / attach label 心智模型作為終局設計。 |

## 目前工作方向

| 方向 | 狀態 | 說明 |
| --- | --- | --- |
| UI / Agent 共用 Application Service | confirmed | 後端重構目標不是把所有邏輯塞進 `BackendFacade`，而是建立共用 command API，讓 UI、assistant tools、scripts 都呼叫同一批 backend workflow。 |
| UI / Agent command surface unification | active | UI 和 agent 對同一 backend workflow 應共用 state、capability policy、blocked reason 和 typed command result，不各自維護第二套判斷。 |

## 舊 ADR 處理

- `ADR-011` 的主線已濃縮為：穩定化優先、validation thesis-critical。
- `ADR-012` 的主線已濃縮為：文件少數 canonical 化、legacy 整合後刪除。
- `ADR-013` 的主線已濃縮為：app 內 assistant 是 workflow operator。
- `ADR-001` 到 `ADR-010` 視為早期探索，已不再保留為 current decision source。

未來若需要新增重大決策，直接補到本文件，不再新增大量碎片化 ADR。
