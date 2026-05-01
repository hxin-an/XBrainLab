# Refactor Gate Runbook

最後更新：`2026-05-01`

這份 runbook 用於判斷是否可以開始後端重構。

## Gate 條件

後端重構前必須回答：

1. 要改哪一條 workflow？
2. 目前 UI、agent、script 哪些地方依賴它？
3. 現有測試能保護什麼？
4. 哪些測試只是 mock-heavy，不足以保護 side effect？
5. 第一個 command / service slice 的 done definition 是什麼？
6. 如果出問題，如何回退或縮小範圍？

## 最小輸出

每個 refactor slice 至少要有：

- scope
- current call sites
- target command shape
- affected files
- validation plan
- non-goals

## Validation Floor

一般情況下至少需要：

- relevant unit tests
- one non-mocked command / controller path test
- focused integration smoke if workflow touches data / training
- `poetry run mkdocs build --strict` if docs changed

## 不通過 gate 的情況

- 只知道想要 Application Service，但不知道第一個 slice。
- 沒有列出 UI call sites。
- 沒有驗證目前 behavior。
- 只靠 MagicMock 測試保護 real workflow side effect。
- 同時改 UI、backend、agent tools、runtime，範圍過大。
