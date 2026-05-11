# XBrainLab Session Prompts

最後更新：`2026-05-02`

這裡只保留短 prompt，避免舊 automation prompt 把 agent 帶回 `AQ-*` queue。

## 一般工作開場

```text
你在 /mnt/d/workspace_v2/projects/lab/XBrainLab。
先讀 AGENTS.md、docs/current.md、docs/target/README.md、docs/planning/now.md、docs/validation/README.md。
不要使用舊 docs/current、docs/history、docs/workflows、.agents/legacy 或 AQ queue 作為 current truth。
目前階段是 product-delivery engineering；milestone 是最低交付門檻，不是工作上限。
優先推進 backend core、UI / agent command surface unification、UI chat / agent panel、
local LLM runtime、desktop launcher 和 product stabilization。
Tool-call eval / thesis evidence 要等產品主線穩定後再開始。
```

## 文件整理

```text
整理文件時，先判斷內容是 current truth、needs-code-check、needs-runtime-check、historical 還是 deleted-after-integration。
優先更新既有 docs/* 文件，不新增大型 planning 文件。
每次有實際驗證或判斷變更，記到 docs/records/worklog.md。
```

## 驗證工作

```text
驗證前先說明要驗證哪個 claim。
驗證後把指令、結果和限制寫回 docs/validation/README.md 或 docs/records/worklog.md。
dashboard clean 只代表 fast regression gate clean，不代表 thesis claim 已完成。
```
