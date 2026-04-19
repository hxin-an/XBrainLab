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

- ruff lint
- mypy type check
- architecture compliance
- startup smoke
- UI baseline capture
- dialog acceptance UI slice
- UI unit suite
- real-data IO integration slice

## 目前 UI 檢查到底在檢查什麼

目前看板對 UI 的判斷，主要是這五層：

- app 和主視窗能不能穩定啟動
- baseline capture 能不能成功重產
- `artifacts/ui/` 裡的必要截圖有沒有缺檔或幾乎全黑
- 核心畫面有沒有和 `tests/baselines/ui/` 的 approved references 發生明顯漂移
- 高風險 dialog 與共用 UI 測試切片有沒有明顯壞掉

也就是說，它現在回答的是：

- UI 還能不能跑起來
- 結構有沒有明顯壞掉
- 高價值互動路徑有沒有回歸

它目前還不能回答：

- 所有 dialog、次級畫面、visualization-heavy views 是否都通過 reference compare
- 所有細微 spacing、字型渲染或 theme 細節是否都維持像素等價
- 整個 app 是否已具備完整 Percy-style 或 screenshot-review 級別的全畫面視覺回歸保護

## 目前什麼叫做「對的基準」

目前 repo 內的 UI baseline 有三層：

- `docs/workflows/UI_BASELINE.md`
  - 定義人類可讀的「結構上什麼叫做對」
- `artifacts/ui/`
  - 放每次驗證時產生的 live screenshot evidence
- `tests/baselines/ui/`
  - 放目前已認可的 core reference screenshots

目前 quality dashboard 對核心畫面的 UI baseline 規則是：

- capture 指令成功
- 必要 screenshot 都存在
- screenshot 不是幾乎全黑
- screenshot 要和 `tests/baselines/ui/` 中的 approved references 對得上

所以現在的 baseline 比較準確的說法是：

- `reference-backed structural regression gate`

但它還不是：

- `full-app visual regression system`

下一步要補的是把 reference coverage 從核心 shell / top-level panels 擴大到更多高價值畫面，而不是停在目前這 7 張核心圖。

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
- 產出的 baseline screenshot 會檢查是否缺檔、幾乎全黑，並和 approved references 比較
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
