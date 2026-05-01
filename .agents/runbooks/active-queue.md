# XBrainLab Active Queue

最後更新：`2026-05-02`

## 狀態

舊 `AQ-*` queue 已退役。

舊版完整 queue 已整合後刪除，不能再當成現在的任務順序。

## 目前 queue

1. `[done]` 清完 `.agents/` active 操作層，移除舊 `docs/current/*`、`Prep Gate`、`Repair Loop` 依賴。
2. `[done]` 將 `docs/legacy/` 整合後刪除。
3. `[done]` 將 `.agents/legacy/` 舊 role / skill / AQ / workflow 文件整合後刪除。
4. `[done]` 設計新的 `.agents/skills/` 和 `.agents/workflows/`，取代舊 skills / AQ automation。
5. `[current]` 推進 UI / agent command surface unification，讓 readiness、blocked reason 和 command result 共用 backend contract。
6. `[current]` 修穩 UI chat / agent panel，包含 loading、error、tool-call feedback、local runtime unavailable。
7. `[current]` 建立 local LLM runtime 選型、cache preflight、health check、fallback。
8. `[next]` 產出 desktop launcher / Windows shortcut，並跑 startup smoke。
9. `[next]` 做 end-to-end product stabilization。
10. `[later]` 產品主線穩定後，建立 tool-call eval / thesis evidence。

## 判斷規則

- 若使用者問「接下來」，先看 `docs/current.md` 和 `docs/planning/now.md`。
- 若舊文件和 canonical 文件衝突，以 canonical 文件為準。
- 若 canonical 文件和 runtime evidence 衝突，以 runtime evidence 為準，並回頭修文件。
