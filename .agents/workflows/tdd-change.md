# Workflow: TDD Change

## 目的

用 test-first 方式完成 bug fix 或小型行為變更。

## 使用 Skills

- `tdd-guard`
- `test-quality-reviewer`
- `validation-runner`

## 前置條件

- 行為可被描述。
- 有合理測試入口。
- scope 不需要同時大改 UI、backend、agent runtime。

## 步驟

1. 寫 expected behavior。
2. 找最小測試檔。
3. 寫 failing test。
4. 跑測試確認 failure 合理。
5. 實作最小修正。
6. 跑目標測試與相關 regression。
7. 用 `test-quality-reviewer` 檢查是否過度 mock。
8. 更新 worklog。

## Done

- 測試先失敗後通過。
- 沒有弱化 assertion。
- 有說明驗證能支撐什麼、不支撐什麼。
