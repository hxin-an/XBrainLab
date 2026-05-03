---
name: test-quality-reviewer
description: Use when judging whether XBrainLab tests can actually catch product or backend problems, especially mock-heavy tests, implementation-detail assertions, and weak validation claims.
---

# test-quality-reviewer

## 用途

用於檢查測試是否真的能抓問題，尤其是避免 AI 生成的 tests 只測 mock、只測 implementation detail、或假通過。

## 先讀

1. `docs/validation/README.md`
2. `docs/architecture/validation.md`

## Review Checklist

- 測試是否描述真實使用者或 backend workflow 行為？
- assertion 是否檢查結果，而不是只檢查某個 mock 被 call？
- 是否有過度 monkeypatch / MagicMock？
- 測試失敗時能否指出真 bug？
- 是否有 non-mocked smoke 覆蓋重要 side effect？
- 測試是否和 XBrainLab state lifecycle 一致？
- 測試是否誤把 dashboard PASS 當 thesis evidence？

## 分類

| 類型 | 用途 | 風險 |
| --- | --- | --- |
| unit contract test | 快速 regression floor | 可能 mock-heavy |
| integration smoke | 走過真 path | 可能慢或 fixture-sensitive |
| UI baseline | 防 UI 明顯偏移 | 不等於 UX 完整驗證 |
| real-data IO | 驗證資料格式入口 | 不等於 scientific reproducibility |
| tool-call scoring | thesis agent evidence | 尚未建立 |

## 輸出

用短格式：

```md
## Test Quality Review

- Strong tests:
- Weak / mock-heavy tests:
- Missing non-mocked evidence:
- Recommended next test:
```
