# XBrainLab Docs

這裡是給人看的文件入口，不是 agent runtime 區。

目前 `docs/` 雖然有很多資料夾，但真正常用的只有少數幾個。

如果你現在只想知道「現在要看哪些」，先只看這五份：

1. [目前狀態](current/STATUS_REPORT.md)
2. [長期計畫](current/PLAN.md)
3. [問題分流](current/BUG_TRIAGE.md)
4. [品質看板](current/QUALITY_DASHBOARD.md)
5. [決策紀錄](decisions/README.md)

## 一頁理解

把 `docs/` 先這樣理解就好：

- `current/`
  - 現在必看
- `decisions/`
  - agent 重設計必看
- `workflows/`
  - 修 bug 或設計驗證時再看
- `history/`
  - 要追脈絡時再看
- `guides/`
  - 安裝與貢獻時再看
- `api/`
  - 查 API 時再看
- `archive/`
  - 舊參考、技術背景與歷史內容，平常先不要讀

## 資料夾導覽

| Folder | 現在要不要看 | 用途 |
| --- | --- | --- |
| `current/` | 必看 | 目前進度、主線、triage |
| `decisions/` | 必看 | thesis 與 agent 架構決策 |
| `workflows/` | 有需要再看 | 穩定化、測試、workflow 參考 |
| `history/` | 有需要再看 | 工作紀錄與 backlog |
| `guides/` | 有需要再看 | 安裝、quickstart、contributing |
| `api/` | 先忽略 | API 參考文件 |
| `archive/` | 先忽略 | 舊架構、舊 agent、舊開發筆記、reference |

## 建議閱讀順序

### 1. 只想跟上現在狀態

讀這三份：

- [current/STATUS_REPORT.md](current/STATUS_REPORT.md)
- [current/PLAN.md](current/PLAN.md)
- [current/BUG_TRIAGE.md](current/BUG_TRIAGE.md)

如果要看「現在程式有沒有壞掉」，再加看：

- [current/QUALITY_DASHBOARD.md](current/QUALITY_DASHBOARD.md)

### 2. 要開始做 agent 重設計

再加讀：

- [decisions/README.md](decisions/README.md)
- [decisions/ADR-011-thesis-direction.md](decisions/ADR-011-thesis-direction.md)

### 3. 要修 bug 或做驗證

有需要再讀：

- [workflows/README.md](workflows/README.md)
- [history/README.md](history/README.md)

## 精簡地圖

### `current/`

現在真正要持續更新的主文件。

- [STATUS_REPORT.md](current/STATUS_REPORT.md)
  - 目前做到哪、驗證到哪、下一步是什麼
- [PLAN.md](current/PLAN.md)
  - 目前的階段與 thesis 工作主線
- [BUG_TRIAGE.md](current/BUG_TRIAGE.md)
  - 已知 bug、runtime signals、優先序
- [QUALITY_DASHBOARD.md](current/QUALITY_DASHBOARD.md)
  - 目前 UI / startup / baseline / 核心驗證的品質看板入口

### `decisions/`

agent 重設計與 thesis 方向的正式決策區。

- [README.md](decisions/README.md)
  - 如何分辨目前有效決策與歷史 ADR
- [ADR-011-thesis-direction.md](decisions/ADR-011-thesis-direction.md)
  - 目前的碩論主線與工作順序

### `workflows/`

當前穩定化與驗證時才需要打開的支撐文件。

- [README.md](workflows/README.md)
- [WORKFLOWS.md](workflows/WORKFLOWS.md)
- [TESTING_STRATEGY.md](workflows/TESTING_STRATEGY.md)
- [DIALOG_MATRIX.md](workflows/DIALOG_MATRIX.md)
- [COVERAGE_GAPS.md](workflows/COVERAGE_GAPS.md)
- [UI_BASELINE.md](workflows/UI_BASELINE.md)

### `history/`

保留脈絡，但預設不用先讀。

- [README.md](history/README.md)
- [SESSION_LOG.md](history/SESSION_LOG.md)
- [BACKLOG.md](history/BACKLOG.md)

### `guides/`

安裝、quickstart、contributing 這類次級入口。

- [README.md](guides/README.md)
- [installation.md](guides/installation.md)
- [quickstart.md](guides/quickstart.md)
- [contributing.md](guides/contributing.md)

### `api/`

查具體類別與模組時再進來。

- [README.md](api/README.md)
- `api/agent/`
- `api/backend/`
- `api/ui/`

### `archive/`

保留舊資料，但不放在日常主線上。

- [README.md](archive/README.md)
- `archive/architecture/`
- `archive/agent/`
- `archive/development/`
- `archive/reference/`

## 預設規則

如果你不確定要看哪個資料夾，就先不要展開整個 `docs/`。

直接從這裡開始：

1. `current/`
2. `decisions/`
3. 真的需要時才進 `workflows/`、`history/` 或 `guides/`
