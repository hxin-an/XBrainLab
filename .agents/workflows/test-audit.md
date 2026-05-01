# Workflow: Test Audit

## 目的

審視目前測試是否能真的抓問題，找出 mock-heavy 或缺 non-mocked evidence 的區域。

## 使用 Skills

- `test-quality-reviewer`
- `validation-runner`

## 步驟

1. 選定範圍，例如 backend、agent、UI、data pipeline。
2. 列出相關 tests。
3. 分類 unit / integration / smoke / baseline / real-data。
4. 標記 mock-heavy tests。
5. 找缺少 non-mocked evidence 的 workflow。
6. 建議下一個最小補測試 slice。
7. 更新 `docs/validation/README.md` 或 worklog。

## Done

- 有明確 strong tests / weak tests / missing evidence。
- 沒有把 test count 當 quality。
- 有下一個可執行測試建議。
