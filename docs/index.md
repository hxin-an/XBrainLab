# XBrainLab Docs

這裡是給人看的文件入口，不是 agent runtime 區。

如果你現在只想快速知道「進度到哪、接下來做什麼」，先看這三份：

1. [Current Status](current/STATUS_REPORT.md)
2. [Long-Running Plan](current/PLAN.md)
3. [Bug Triage](current/BUG_TRIAGE.md)

## Folder Map

### `current/`

現在進行中的重點文件。

- [STATUS_REPORT.md](current/STATUS_REPORT.md)
  - 目前做到哪、驗證到哪、下一步是什麼
- [PLAN.md](current/PLAN.md)
  - 長期計畫與四個大階段
- [BUG_TRIAGE.md](current/BUG_TRIAGE.md)
  - 目前已知 bug、runtime signals、優先序

### `workflows/`

支撐穩定修 bug 的工作流與風險地圖。

- [TAKEOVER.md](workflows/TAKEOVER.md)
- [WORKFLOWS.md](workflows/WORKFLOWS.md)
- [UI_BASELINE.md](workflows/UI_BASELINE.md)
- [TESTING_STRATEGY.md](workflows/TESTING_STRATEGY.md)
- [DIALOG_MATRIX.md](workflows/DIALOG_MATRIX.md)
- [RISK_CLUSTERS.md](workflows/RISK_CLUSTERS.md)
- [COVERAGE_GAPS.md](workflows/COVERAGE_GAPS.md)

### `history/`

較長期的工作紀錄與累積中的待辦。

- [SESSION_LOG.md](history/SESSION_LOG.md)
- [BACKLOG.md](history/BACKLOG.md)

### Project Docs

產品與工程參考資料仍然保留，但不需要先讀。

- [getting-started/](getting-started/)
- [architecture/](architecture/)
- [development/](development/)
- [reference/](reference/)
- [decisions/](decisions/)
- [agent/](agent/)
- [contributing.md](contributing.md)

## What To Ignore

- 如果你只是想跟上目前狀態，暫時不用讀 `.agents/`
- `history/` 不是起手閱讀清單，只有想看詳細脈絡時再打開
- `reference/AGENT_SKILLS.md` 是 agent/skill 選型背景，不是日常進度入口
