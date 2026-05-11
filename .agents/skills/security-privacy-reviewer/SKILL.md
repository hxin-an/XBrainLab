---
name: security-privacy-reviewer
description: Use when reviewing XBrainLab local LLM, MCP, file access, remote/headless server, dataset privacy, prompt injection, excessive agency, secret leakage, logging, and clinical or personal EEG data handling risks.
---

# security-privacy-reviewer

## 用途

用於檢查 XBrainLab 的安全、隱私和 agent 權限邊界，特別是 MCP / local LLM / file system / EEG
dataset 相關工作。

## 設計來源

已消化參考：

- OWASP Top 10 for LLM Applications：prompt injection、sensitive information disclosure、
  excessive agency、insecure output handling、unbounded consumption 等是 LLM app 主要風險。
- OWASP MCP Top 10：MCP 工具可能帶來 command injection、工具權限過大、供應鏈和資料外洩風險。
- MCP authorization spec：HTTP-based transport 才需要明確 auth flow；stdio 應避免把 credentials
  混在不受控輸出裡。

## 先讀

1. `docs/target/agent.md`
2. `docs/architecture/agent.md`
3. `docs/architecture/backend.md`
4. MCP / agent / file access / logging code touched by the change

## Review Gate

檢查：

- local-first 是否保持；不把 EEG data、prompt、recipe、log 送到 remote API。
- MCP tools 是否最小權限；destructive / long-running / file-writing command 是否 confirmation。
- external prompt / dataset metadata / README / events.tsv 是否可能含 prompt injection；不得把資料文字當 instruction。
- file path tools 是否限制在使用者明確選擇或允許範圍，不任意掃全碟。
- logs / artifacts 是否避免保存敏感 subject id、完整私人路徑、clinical labels，或有清楚 redaction policy。
- HTTP MCP 是否有 auth、localhost/default deny、CORS/session/token story。
- agent tool output 是否經 verifier / formatter；不直接執行模型生成的 shell/code。
- no-China model policy、cache location、license / download source 是否可審查。

## 打回條件

- MCP / agent 可以在未確認下 destructive 操作。
- HTTP server 開遠端卻沒有 auth/session/permission model。
- prompt injection 文字能影響 tool policy 或 bypass capability。
- raw logs/artifacts 外洩敏感資料。
- model/API path 繞過 local-only policy。

## 輸出格式

```md
## Security Verdict

- verdict: acceptable / needs guardrails / unsafe

## Data Exposure

## Tool Permission Risks

## Prompt Injection Surface

## Required Mitigations
```
