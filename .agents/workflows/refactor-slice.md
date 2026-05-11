# Workflow: Refactor Slice

## 目的

在架構複盤完成後，執行一個小而可驗證的重構 slice。

## 使用 Skills

- `software-design-reviewer`
- `refactor-slicer`
- `tdd-guard`
- `test-quality-reviewer`
- `validation-runner`

## 前置條件

- 使用者已同意進入該 slice。
- `.agents/runbooks/refactor-gate.md` 通過。
- 已列出 current call sites。
- 已定義 validation plan。

## 步驟

1. 寫 slice scope 和 non-goals。
2. 盤點 affected files。
3. 補或確認測試保護。
4. 實作最小變更。
5. 跑 validation plan。
6. 更新 `docs/architecture/` 或 `docs/current.md`。
7. 更新 worklog / implementation log。

## 禁止

- 不同時重寫 UI、backend、agent runtime。
- 不把 Application Service 做成新平行 backend。
- 不破壞 current UI workflow。
