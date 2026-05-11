# Architecture Target Context

最後更新：`2026-05-01`

這份文件只作導讀，不保存完整目標架構。

真正 source of truth：

- `docs/target/architecture.md`
- `docs/target/agent.md`
- `docs/decisions/README.md`

## 一句話

UI、agent tools、headless scripts 最後應該共用同一套 backend workflow command。

## 關鍵決策

- Application Service / Command API 目標：看 `docs/target/architecture.md`。
- Agent State / Verification / Scoring：看 `docs/target/agent.md`。
- 目前 backend 實況：看 `docs/architecture/backend.md`。

## 重構原則

重構 gate 看 `.agents/runbooks/refactor-gate.md`。
