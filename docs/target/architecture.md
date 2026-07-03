# XBrainLab 目標架構

最後更新：`2026-07-03`

這頁描述目標態，不代表目前已完成。現況請看 [目前架構](../architecture/README.md)。

## 目標

XBrainLab 的目標不是「PyQt app 旁邊加一個聊天視窗」，而是：

```text
human UI、assistant、scripts
  都操作同一套 EEG workflow backend
```

## 目標圖

```text
PyQt UI panels
Assistant tools
Headless scripts
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

## Removed `BackendFacade`

`BackendFacade` 不再是目標架構的一層；舊 high-level wrapper 已由
`ApplicationService / Command API` 和 focused command services 取代。

- UI、assistant、headless scripts 不應 import 或 instantiate `BackendFacade`。
- 舊 facade API behavior 要保存在 command/service/helper tests，不保留 facade wrapper。
- 不新增第二套 readiness / success / error truth。

如果 `BackendFacade` module 或 facade compatibility tests 被重新加入，它就違反目標架構。

## Data Interpretation 目標

資料入口應該是：

```text
scan -> preview -> validate -> confirm -> apply -> save recipe
```

核心 truth 是 applied interpretation，不是單純「load file」或「attach label」。

## Assistant 目標

assistant 應該：

- 讀 backend state snapshot。
- 使用 backend capability policy。
- 呼叫同一套 command API。
- 收到 structured result。
- 遇到 destructive / long-running / semantic ambiguity 時要求確認。

MCP 已從 active target 移除。既有 MCP 探索不再定義目標架構，也不作為 release 或 thesis
前置條件；若未來重新啟用，必須另開 decision。

## 目前不要誤解

- 這是目標，不是 current truth。
- controller 不需要全部消失，但 product path 不應繞過 command spine。
- Phase 1A 不是只做 audit，而是要清 legacy product path、UI refresh truth 和 test truth。
- formal thesis benchmark 要等 product surface 穩定後再刷新。
