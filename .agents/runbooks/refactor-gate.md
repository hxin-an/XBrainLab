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
- architecture / source-of-truth guard for the class of bug being fixed
- `poetry run mkdocs build --strict` if docs changed

## Completion Gate

修復 architecture / refresh / state-truth 類問題時，不可在第一個局部測試通過後就宣稱完成。
完成前必須再做一輪同類問題搜尋，並跑完整 source guard。若新增 guard 後抓到現有產品碼
違規，必須修到 guard clean；不能只讓新測試通過。

## 不通過 gate 的情況

- 只知道想要 Application Service，但不知道第一個 slice。
- 沒有列出 UI call sites。
- 沒有驗證目前 behavior。
- 只靠 MagicMock 測試保護 real workflow side effect。
- 新增 guard 只保護 toy sample，沒有拿現有產品碼跑過一次。
- 同時改 UI、backend、agent tools、runtime，範圍過大。
