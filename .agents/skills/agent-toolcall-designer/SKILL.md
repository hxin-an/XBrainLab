---
name: agent-toolcall-designer
description: Use when designing or reviewing XBrainLab agent state snapshots, backend-controlled tool availability, tool-call verification, command contracts, and tool-call scoring/evaluation workflows.
---

# agent-toolcall-designer

## 用途

用於設計 XBrainLab agent 的 state、tool call、verification、scoring contract。

## 先讀

1. `docs/target/agent.md`
2. `docs/architecture/agent.md`
3. `docs/validation/README.md`
4. `.agents/context/thesis.md`

## 核心原則

- agent 是 workflow operator，不是普通 chatbot。
- target runtime 是 local-only；API / Gemini code path 後續要移除。
- tool availability 由 backend capability policy 控制。
- 一次只有一個 active dataset pipeline。
- epoch / dataset 後，一般 `load_data` / `generate_new_dataset` 應被擋下。
- `blocked_commands` 不完整塞進 LLM prompt；只摘要和當前 intent 相關的 blocked reason。
- State Snapshot 不應變成第二份 backend truth。

## Contract 外框

設計時至少考慮：

- State Snapshot Contract
- Tool Call Contract
- Verification Result Contract
- Scoring Contract

## Thesis Evidence

tool-call validation 應導向可重跑 scoring system：

- intent accuracy
- tool selection accuracy
- parameter accuracy
- state-transition accuracy
- error-recovery accuracy
- invalid / unsafe call rate
- self-correction success rate
