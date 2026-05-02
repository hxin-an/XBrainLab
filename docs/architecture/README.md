# XBrainLab Architecture

最後更新：`2026-05-01`

這份文件是架構總覽，不放太多細節。細節拆到 `docs/architecture/`。

這裡描述目前實際架構。理想架構與需求請看 `docs/target/`。

## 架構評斷

一份 `ARCHITECTURE.md` 不夠描述 XBrainLab。

原因是 XBrainLab 同時包含：

- PyQt desktop UI
- EEG data import / preprocessing / training / evaluation pipeline
- backend facade and managers
- in-app tool-calling assistant
- local-first assistant runtime
- validation and thesis evidence system

如果全部塞進單一文件，會變成另一份 agent 長文，難以維護。因此目前採用：

- 一份 architecture overview
- 五份分層架構文件

## 系統分層

```text
User
  |
  v
PyQt UI
  |
  v
Controllers / Facade
  |
  v
Study / DataManager / TrainingManager
  |
  v
Data pipeline / Models / Evaluation / Visualization

In-app Assistant
  |
  v
Local LLM Runtime + Tool Surface
  |
  v
Same backend operation surface used by human workflows
```

## 核心分層文件

| 文件 | 內容 |
| --- | --- |
| [ui.md](ui.md) | PyQt UI、panels、dialogs、event / refresh 邊界。 |
| [backend.md](backend.md) | backend facade、Study、DataManager、TrainingManager、controllers。 |
| [data_pipeline.md](data_pipeline.md) | EEG import、labels、preprocess、epoching、dataset、training、evaluation。 |
| [agent.md](agent.md) | app 內 assistant、local-only runtime 目標、tool calls。 |
| [validation.md](validation.md) | 測試層、quality dashboard、UI baseline、real-data validation。 |

## 目前架構原則

- 先穩定既有 PyQt app，再做 agent redesign。
- human user 和 in-app assistant 應是同一套軟體能力面的兩種控制模式。
- assistant product runtime 已是 local-only；remote backend modules 已從 product package 移除。
- `openai` / `google-genai` 只保留在 optional `legacy-remote-llm` dependency group，不是 default deps。
- tool-call surface 不應被舊工具邊界綁死，應以 workflow intent 重設計。
- validation 是 thesis-critical，不是最後補測試。
- 文件主張必須能對到 source code、test、artifact 或 runtime evidence。

## 目前最大風險

- 文件和 runtime evidence 尚未完全重建可信度。
- legacy 閱讀面已清乾淨；`docs/legacy/` 和 `.agents/legacy/` 都已刪除。
- 新 workspace 的標準 `dev,test,docs` environment 已可用，但 optional `llm` group 尚未驗證。
- local LLM prompt / structured smoke 已通過，但真 local LLM 長時間 ChatPanel walkthrough
  仍未跑，不能把 runtime smoke 等同完整 assistant product acceptance。
