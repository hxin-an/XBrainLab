---
name: mcp-adapter-reviewer
description: Use when reviewing XBrainLab MCP stdio or HTTP adapter design, tools/list exposure, tools/call execution, desktop-control versus headless sessions, authorization, progressive tool exposure, and ApplicationService policy enforcement.
---

# mcp-adapter-reviewer

## 用途

用於檢查 MCP 是否只是 external agent adapter，而不是變成第三套 backend truth。

## 設計來源

已消化參考：

- MCP transport spec：stdio 是 client 啟動 subprocess；stdout 只能寫 MCP JSON-RPC message，
  logging 應走 stderr；Streamable HTTP 是獨立 server，可處理多 client。
- MCP tools spec：client 透過 `tools/list` 發現工具、`tools/call` 呼叫工具；server 回 structured
  result / error。
- MCP authorization spec：HTTP-based transport 才走 authorization；stdio 通常從環境取得憑證。

## 先讀

1. `docs/target/architecture.md`
2. `docs/target/agent.md`
3. `docs/architecture/backend.md`
4. `XBrainLab/mcp/server.py`
5. `XBrainLab/backend/application/automation.py`

## Review Gate

檢查：

- MCP tools 是否全部轉成 `ApplicationService.execute()`，不直接碰 controller。
- `tools/list` 是否可用 capability / taxonomy 做 progressive exposure 或至少提供 live capability。
- tool schema 是否與 agent / automation command schema 同源。
- stdio server stdout 是否只輸出 JSON-RPC；log 不污染 stdout。
- Desktop-Control 和 Headless-Analysis 是否明確分 mode / session / UI refresh claim。
- HTTP MCP 是否定義 session ownership、auth、job progress、cancellation、resource lock。
- 遠端 headless server 是否不宣稱會刷新本機 UI。
- long-running training 是否有 job id、progress、cancel、recoverable state，而不是同步卡住 request。
- MCP result 是否包含 mode、session_id、ui_refresh、CommandResult / state snapshot。

## 打回條件

- MCP call 繞過 ApplicationService / capability / autonomy policy。
- HTTP server `new Study()` 後宣稱控制使用者正在看的 UI。
- stdio stdout 混入 logging。
- 所有 tools 永遠暴露給 external agent，沒有 state/capability boundary。
- long-running command 沒有 job model。

## 輸出格式

```md
## MCP Verdict

- verdict: adapter-clean / usable baseline / unsafe or confused

## Session Model

## Tool Exposure

## Transport Risks

## Required Validation
```
