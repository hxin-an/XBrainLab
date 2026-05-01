# tdd-guard

## 用途

用於需要以 TDD 或 test-first 方式修改 XBrainLab 程式碼時。

這個 skill 參考常見 AI coding workflow：先明確行為、先寫會失敗的測試、再做最小實作、最後跑驗證。它不是要求每個工作都 TDD；適合 bug fix、refactor slice、核心 workflow 行為變更。

## 先讀

1. `docs/validation/README.md`
2. `.agents/skills/test-quality-reviewer/SKILL.md`
3. `.agents/runbooks/refactor-gate.md`

## 流程

1. 寫清楚 expected behavior。
2. 找到最小測試位置。
3. 先寫或修改測試，測試應在修復前失敗。
4. 跑目標測試，確認 failure 和預期一致。
5. 做最小實作。
6. 跑同一組測試直到通過。
7. 跑相關 regression / smoke。
8. 檢查測試是否太依賴 mock 或 implementation detail。

## 測試原則

- 優先測 public behavior / command result / state transition。
- 對 XBrainLab workflow side effect，盡量補 non-mocked path。
- Mock 只能隔離昂貴或外部依賴，不能讓測試只驗證 mock 被呼叫。
- 不接受只為了讓測試通過而改弱 assertion。

## 停止條件

- 找不到可觀測 expected behavior。
- 測試只能靠大量 mock 才能寫。
- 需要大改架構才能寫第一個測試。
- 測試失敗和預期 bug 無關。
