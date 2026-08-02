---
name: architecture-reviewer
description: Use when reviewing XBrainLab current versus target architecture across UI, backend, data pipeline, agent, validation, and documentation before proposing or accepting implementation work.
---

# architecture-reviewer

## 用途

用於做 UI、backend、data pipeline、agent、validation 的架構複盤。

## 先讀

1. `docs/target/README.md`
2. `docs/target/architecture.md`
3. `docs/target/agent.md`
4. `docs/architecture/README.md`
5. `.agents/runbooks/architecture-review.md`

## 工作方式

1. 先描述 current implementation。
2. 再描述 target expectation。
3. 列出 gap。
4. 標出 risk。
5. 建議 first slice。
6. 寫出 required validation。

## 特別注意

- Product command spine 目前是 `ApplicationService / Command API`；`Study` 與 managers
  持有 domain state，部分 UI controller adapter / observer boundary 仍待收斂。
- `BackendFacade` 已物理移除。把它描述成 current wrapper、compatibility layer 或 target
  abstraction 都是架構失真；review 要防止它或等價 generic facade 回流。
- target 不是把所有 workflow 邏輯塞進 `ApplicationService`；新邏輯應落在 focused command
  service / handler，再由 command spine 統一 gate 與包裝 result。
- agent target 包含 State Manager、Verification Layer、capability policy、tool-call scoring。
- MCP 已退出 active product / thesis roadmap。除非使用者明確要求 MCP，review 不讀 MCP
  adapter、不把 MCP 納入 current architecture gap，也不新增 MCP gate。

## 禁止

- 不直接開始重構。
- 不把 target 當已完成。
- 不只看文件；需要對 source 或 tests。
