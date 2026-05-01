# Architecture Review Runbook

最後更新：`2026-05-02`

這份 runbook 用於需要純架構複盤時使用。它不阻擋 product-delivery 任務；
若使用者要求實作或目前 milestone 已明確，應依 `AGENTS.md` 和
`docs/planning/now.md` 推進工程交付。

## 目標

產出一份可讓使用者決定或校準產品交付順序的架構評估。

## 先讀

1. `docs/current.md`
2. `docs/target/README.md`
3. `docs/target/architecture.md`
4. `docs/architecture/README.md`
5. `docs/validation/README.md`
6. `docs/planning/now.md`

## 檢查面向

### UI

- `MainWindow` 如何取得 controllers。
- panels 是否直接呼叫 controller workflow methods。
- observer bridge / Qt signal 是否有清楚生命週期。
- 長任務、thread、refresh 是否有閃退風險。

### Backend

- `Study`、`DataManager`、`TrainingManager` 各自責任是否清楚。
- controllers 裡哪些是 adapter，哪些是 business workflow。
- `BackendFacade` 是否只作 wrapper，還是已承載平行邏輯。
- 哪些 workflow 最適合先抽成 command。

### Data pipeline

- import、label、preprocess、epoch、dataset、training、evaluation 邊界是否清楚。
- real-data evidence 到哪裡。
- scientific reproducibility 還缺什麼。

### Agent

- assistant runtime 目前和 local-only target 差距，尤其是 API / Gemini code path 的移除範圍。
- tool registry / real tools 是否繞過 UI path。
- tool-call validation 缺哪些 state / result / error evidence。

### Validation

- 哪些測試是 mock-heavy contract tests。
- 哪些 non-mocked path 已存在。
- 後端重構第一切片需要哪些測試保護。

## 輸出格式

建議輸出到 `docs/planning/now.md` 或另開經使用者同意的 review 文件。

格式：

```md
## Area

### Current

### Target Gap

### Risk

### Suggested First Slice

### Required Validation
```

## 邊界

- 若任務是純 architecture review，不直接開工重構。
- 若任務是 product delivery 或使用者已要求實作，不要用本 runbook 當停止理由。
- 不新增大量新文件。
- 不把 target architecture 寫成 current implementation。
- 不根據舊 records 下決策，除非重新對照 source 或 runtime evidence。
