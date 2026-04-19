# XBrainLab Quality Dashboard

這份文件是品質看板入口，不是歷史筆記。

如果你想快速知道：

- UI 最近有沒有跑掉
- app 目前能不能正常啟動
- baseline 截圖是不是還可信
- 主要 UI / IO 驗證現在是綠燈還是紅燈

就看這個看板。

## Live Report 位置

最新一次執行結果會輸出到：

- `artifacts/quality/latest.md`
- `artifacts/quality/latest.json`

這兩份是自動生成檔，不會作為正式文件長期維護。

## 目前監測的內容

- startup smoke
- UI baseline capture
- dialog acceptance UI slice
- UI unit suite
- real-data IO integration slice

## 手動刷新指令

```bash
/home/administrator/.local/bin/poetry run python scripts/dev/update_quality_dashboard.py
```

如果只是想在自動化流程中「過一段時間再更新一次」，可以用：

```bash
/home/administrator/.local/bin/poetry run python scripts/dev/update_quality_dashboard.py --skip-if-fresh-minutes 60
```

## 目前規則

- UI 驗證預設走 headless-safe 路徑
- 產出的 baseline screenshot 也會一起檢查是否缺檔或幾乎全黑
- 這份看板偏向「現在是否健康」，不是 release changelog

## 解讀方式

- `PASS`
  - 這條檢查目前是健康的
- `WARN`
  - 這條檢查目前可跑，但有風險或訊號需要追
- `FAIL`
  - 這條檢查目前不可信，應優先 triage

## 與其他文件的分工

- `STATUS_REPORT.md`
  - 人看的目前進度摘要
- `BUG_TRIAGE.md`
  - 問題定義、證據與優先序
- `QUALITY_DASHBOARD.md`
  - 最新品質訊號入口
