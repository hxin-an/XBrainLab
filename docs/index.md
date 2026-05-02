# XBrainLab Docs

這裡是 XBrainLab 的文件入口。

現在文件分成幾個明確區域：

```text
docs/
  current.md       目前狀態
  operations.md    操作指令
  target/          需求與理想架構
  architecture/    目前實際架構
  planning/        短期與長期規劃
  decisions/       已確認決策
  validation/      驗證策略與證據邊界
  records/         實作紀錄與流水帳
```

## 先看這幾份

1. [current.md](current.md)
   - 目前真實狀態、不能信什麼、下一步是什麼。
2. [target/README.md](target/README.md)
   - 需求、理想架構與 agent 目標。
3. [architecture/README.md](architecture/README.md)
   - 系統總覽與分層架構入口。
4. [planning/now.md](planning/now.md)
   - 目前短期焦點。
5. [planning/roadmap.md](planning/roadmap.md)
   - 少量路線規劃、階段主線和暫存問題。
6. [decisions/README.md](decisions/README.md)
   - 目前有效決策。
7. [validation/README.md](validation/README.md)
   - 測試、dashboard、資料集和 thesis evidence 的可信邊界。

## 文件分工

| 文件 | 用途 |
| --- | --- |
| [current.md](current.md) | 目前狀態、blocker、下一步。 |
| [operations.md](operations.md) | 安裝、啟動、測試、環境操作。 |
| [target/](target/README.md) | 需求、理想架構、agent 目標。 |
| [architecture/](architecture/README.md) | 目前實際架構與 source 對照。 |
| [planning/](planning/now.md) | 短期現在做什麼、長期路線。 |
| [decisions/](decisions/README.md) | 討論後確認的決策。 |
| [validation/](validation/README.md) | 驗證策略、目前 evidence、mock 邊界。 |
| [records/](records/implementation_log.md) | 實作紀錄與流水帳。 |

## 目前最重要提醒

`artifacts/quality/latest.*` 已在新 workspace 刷新，fast dashboard 目前是 clean `PASS`。這代表工程健康快照通過，但不代表 thesis claim 或 optional LLM runtime 已完整驗證。

目前工作已進入 product-delivery engineering。legacy / active 閱讀面已收掉；後端
`ApplicationService / Command API` 第一版已落地。下一步是把 UI 和 agent 的
backend command surface 統一，修穩 UI chat / agent panel，完成 local-only LLM
runtime 的 product path 封口與桌面啟動方式。Tool-call eval / thesis evidence 要等產品主線穩定後再做。

assistant product runtime 目前已是 local-only：remote backend modules 已從 product package
移除，`LLMConfig` / `LLMEngine` / `AgentWorker` 不會 instantiate API / Gemini backend。
`openai` / `google-genai` 只留在 optional `legacy-remote-llm` dependency group。真 local LLM
長時間 ChatPanel walkthrough 仍未跑，不能用 local runtime smoke 直接宣稱完整產品驗收完成。

給 agent 看的 thesis context 現在放在 `.agents/context/thesis.md`，不放在人類 active 入口。
