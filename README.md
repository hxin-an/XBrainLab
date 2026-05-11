# XBrainLab

XBrainLab 是一個整合 `tool-calling agent` 的 EEG 分析桌面應用程式。

這個 repo 目前同時承擔兩件事：

1. 把現有 PyQt 應用穩定到可實際使用
2. 支撐碩論中的 `tool-call agent` 架構重設與驗證

## 先看這裡

- 文件入口：
  [docs/index.md](docs/index.md)
- 目前狀態：
  [docs/current.md](docs/current.md)
- 目標態：
  [docs/target/README.md](docs/target/README.md)
- 架構總覽：
  [docs/architecture/README.md](docs/architecture/README.md)
- 實作紀錄：
  [docs/records/implementation_log.md](docs/records/implementation_log.md)

## Repo 結構

- `XBrainLab/`
  - 主程式碼
- `tests/`
  - unit、integration、regression 與 real-data validation
- `scripts/`
  - 開發、驗證、agent benchmark 相關輔助腳本
- `docs/`
  - 給人看的專案文件
- `.agents/`
  - Codex / autopilot 用的 agent 操作文件

## 文件導覽

可以先這樣理解各資料夾：

- `docs/`
  - 目前狀態、目標、規劃、驗證、決策、紀錄。
- `docs/target/`
  - 需求與理想架構。
- `docs/architecture/`
  - 目前實際系統架構。

舊文件已整合後刪除，不再保留 `docs/legacy/` 閱讀面。

文件入口在這裡：

- [docs/index.md](docs/index.md)

## 快速開始

安裝依賴：

```bash
poetry install --with dev,test
```

啟動程式：

```bash
poetry run python run.py
```

如果要啟用本地 LLM 支援：

```bash
poetry install --with llm
```

## 其他重要檔案

- `docs/planning/roadmap.md`
  - 目前階段路線與下一步
- `CHANGELOG.md`
  - 歷史版本紀錄；目前工程整理以 `docs/records/implementation_log.md` 為準
