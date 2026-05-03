---
name: docs-curator
description: Use when organizing, consolidating, or updating XBrainLab documentation so current truth, target design, planning, decisions, validation, and records remain separated and trustworthy.
---

# docs-curator

## 用途

用於整理 XBrainLab 文件、合併過期 agent 產物、判斷文件應放在哪裡。

## 先讀

1. `docs/index.md`
2. `docs/current.md`
3. `docs/target/README.md`
4. `docs/planning/now.md`
5. `.agents/stack.md`

## 判斷規則

- current truth：寫入 `docs/current.md` 或 `docs/architecture/`。
- 目標態 / 需求：寫入 `docs/target/`。
- 短期工作：寫入 `docs/planning/now.md`。
- 長期方向：寫入 `docs/planning/roadmap.md`。
- 決策：寫入 `docs/decisions/README.md`。
- 驗證邊界：寫入 `docs/validation/README.md`。
- 重要工程紀錄：寫入 `docs/records/implementation_log.md`。
- 流水帳：寫入 `docs/records/worklog.md`。

## 禁止

- 不新增大量一級文件。
- 不恢復 `docs/legacy/`、`docs/active/`。
- 不把 `target/` 寫成 current implementation。
- 不把 records 當作現在真相。

## 完成檢查

- 連結沒有指向已刪除檔案。
- MkDocs strict build 可通過。
- 有必要時更新 worklog。
