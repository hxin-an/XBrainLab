# XBrainLab 目標架構

最後更新：`2026-05-09`

這頁描述目標態，不代表目前已完成。現況請看 [目前架構](../architecture/README.md)。

## 目標

XBrainLab 的目標不是「PyQt app 旁邊加一個聊天視窗」，而是：

```text
human UI、assistant、MCP、scripts
  都操作同一套 EEG workflow backend
```

## 目標圖

```text
PyQt UI panels
Assistant tools
Headless scripts
MCP server
  |
  v
ApplicationService / Command API
  |
  v
Focused command services
  |
  v
Study / DataManager / TrainingManager
  |
  v
MNE / PyTorch / filesystem / runtime diagnostics
```

## 核心 contract

每個重要 workflow command 都應有：

- 明確 input schema。
- structured result。
- typed error / blocked reason。
- capability policy。
- changed state / refresh scope。
- human confirmation boundary。

## `ApplicationService` 的角色

`ApplicationService` 是 command spine：

- 接 command。
- 檢查 capability / confirmation。
- 委派 focused service。
- 包裝 state / result envelope。

它不應該吸收所有業務邏輯。

## `BackendFacade` 的角色

`BackendFacade` 可以保留，但只能是 wrapper：

- assistant / script 的 high-level convenience layer。
- command API 的便利入口。
- 不自己重做 import / preprocess / train / evaluate workflow。
- 不讓 UI、agent、MCP 看到不同的 readiness / success / error truth。

如果 `BackendFacade` 開始自己維護 workflow 狀態，它就違反目標架構。

## Data Interpretation 目標

資料入口應該是：

```text
scan -> preview -> validate -> confirm -> apply -> save recipe
```

核心 truth 是 applied interpretation，不是單純「load file」或「attach label」。

## Agent / MCP 目標

assistant 和 MCP 都應該：

- 讀 backend state snapshot。
- 使用 backend capability policy。
- 呼叫同一套 command API。
- 收到 structured result。
- 遇到 destructive / long-running / semantic ambiguity 時要求確認。

MCP 是 external adapter，不是第三套 backend。

## 目前不要誤解

- 這是目標，不是 current truth。
- controller 不需要全部消失，但 product path 不應繞過 command spine。
- Phase 1A 不是只做 audit，而是要清 legacy product path、UI refresh truth 和 test truth。
- formal thesis benchmark 要等 product surface 穩定後再刷新。
