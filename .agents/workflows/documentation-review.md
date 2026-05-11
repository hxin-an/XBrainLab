# Workflow: Documentation Review

## 目的

整理文件，保持少數 canonical docs，避免 AI 文件再次膨脹。

## 使用 Skills

- `docs-curator`
- `validation-runner`

## 步驟

1. 讀 `docs/index.md`、`docs/current.md`、`docs/planning/now.md`。
2. 判斷要處理的內容屬於 current、target、architecture、planning、decision、validation 或 record。
3. 優先更新既有文件。
4. 刪除已整合的短期文件或重複文件。
5. 跑 `poetry run mkdocs build --strict`。
6. 更新 `docs/records/worklog.md`。

## Done

- 沒有新增不必要文件。
- 文件站 build 通過。
- current / target / records 沒有混在一起。
