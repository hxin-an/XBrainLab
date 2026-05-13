# XBrainLab Now

最後更新：`2026-05-13`

這頁只放下一輪施工焦點。

## 目前焦點

**Phase 1A 收尾：UI refresh truth、test evidence boundary、human desktop acceptance。**

Backend command spine 已經是 product runtime 主路徑；`BackendFacade` 已物理移除。現在要避免
把「已經沒有 facade」誤讀成「UI 已經 full zero-controller」或「產品已人工驗收」。

短期工作要從目前 target gap 反推，而不是再重複 audit：

- real `Study` product path 已禁止 `BackendFacade` 和 direct legacy fallback success。
- high-value UI actions 已走 command / query truth。
- 剩餘 controller path 多半是 panel constructor / observer bridge、human-in-loop UI request、
  mock / legacy compatibility、或 lower-level fixture setup。
- 產品仍缺 Windows human desktop acceptance；automated smoke 不能取代。

## 本輪要達到

| 工作 | 完成判準 |
| --- | --- |
| Controller exception reduction | 從剩餘例外地圖挑一類可安全替換的 real-product read/display path；若不能替換，要寫清楚分類和原因。 |
| UI refresh proof | 對 touched path 補 command/query truth assertion 或 product smoke；不接受 no-crash / generic string evidence。 |
| Test evidence cleanup | product-success tests 不回到 facade、legacy fallback、direct mutable `Study` state 或 positive controller lookup。 |
| Human acceptance prep | 明確列出 Windows desktop click-through 尚缺哪些步驟和 artifact；不把 dashboard PASS 當人工驗收。 |
| Docs readability | current / architecture / validation / now 可以讓新工程師先讀摘要，再追 checkpoint。 |

## Human Windows acceptance checklist

這不是本輪已完成事項；這是 MVP 前要補的人工證據清單。每一項都要記錄 branch、
commit、環境、操作步驟、截圖或 artifact、預期結果、實際結果與 blocker。

| 路徑 | 需要補的證據 |
| --- | --- |
| Launcher -> MainWindow | Windows launcher / shortcut 人手啟動，MainWindow 在目前螢幕可見且 geometry 正常。 |
| Data Import -> Apply | file/folder scan、preview、metadata review、label matching、review/import、apply selected scope 的人手紀錄。 |
| Preprocess -> Epoch | 使用代表性資料跑 preprocess / epoch，確認 UI 不卡住、不被 modal 擋住，狀態與 command result 一致。 |
| Split -> Train readiness | split 後可見 train/validation/test summary，Training gate 由 command state 解鎖。 |
| Training confirmation | Start Training confirmation、running/progress/stopped 狀態可見，並記錄中斷或失敗時的 recoverability。 |
| Assistant local runtime | local model missing / available 兩種狀態都要人手點過，確認不閃退且錯誤語意不是 debug dump。 |

## 接下來才做

| Phase | 開始條件 |
| --- | --- |
| 1B Data Interpretation MVP Slice | Phase 1A 的 product runtime / refresh / evidence 邊界足夠穩，不再把 UX bug 和 backend truth 混在一起。 |
| 1C Tool-Call Product Baseline | command surface 和 state snapshot 足夠穩定。 |
| 1D Windows Desktop Acceptance | backend / UI / Data Interpretation / assistant baseline 可跑代表性 workflow。 |
| 2 Release Candidate | human desktop MVP acceptance 有證據。 |

## 本輪驗證

| 改動類型 | 至少要跑 |
| --- | --- |
| docs only | `poetry run mkdocs build --strict`、`git diff --check` |
| backend command / legacy cleanup | `tests/architecture_compliance.py`、focused backend command tests |
| UI refresh cleanup | focused UI refresh tests 或 walkthrough artifact |
| validation reality-gap audit | test matrix、human-observable walkthrough smoke、至少一條 launcher -> import preview -> apply 的 product smoke。 |
| agent / MCP surface | agent tool tests、MCP adapter tests |

## 不能先講

- product complete。
- backend target architecture fully aligned。
- Data Interpretation final。
- automated walkthrough 等於 human Windows desktop acceptance。
- tool-call eval 等於產品完成。
