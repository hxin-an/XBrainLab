# XBrainLab Now

最後更新：`2026-05-12`

這頁只放下一輪施工焦點。

## 目前焦點

**Phase 1A 收尾：Backend Command Spine / Legacy / UI Refresh / Test Cleanup。**

要先做這件事，因為 MVP 前最大的風險不是功能不夠多，而是 UI、backend、assistant、MCP
各自保存一套 workflow truth。

Data Import 這條線已先補一輪 UX target alignment 並交付第一版 task-oriented step-panel
wizard baseline：primary import actions、external label sources、selected scope vs scan location、
structured action items、recipe preservation 和 UI / agent / MCP command surface 對齊。
最新 UI polish 已把每個 wizard step 改成不同任務 panel，不再只是把表格搬到各 step；footer
也已把 `Cancel` 放左下、流程導航 / apply 放右下。主 Dataset sidebar 已移除第一層
`Add Labels to Loaded Data` / `Smart Parse Metadata` 舊入口。這仍需要 human Windows desktop
acceptance。

## 本輪要達到

| 工作 | 完成判準 |
| --- | --- |
| Legacy product path cleanup | real `Study` runtime 的主要 mutating path 不再 silent fallback 到 legacy controller mutation。 |
| UI refresh cleanup | command 成功後的頁面更新由 shared refresh route / changed state 驅動，不由各頁自己猜。 |
| Test cleanup | 測試不再把 legacy fallback 當作預期成功路徑；mock 只隔離外部依賴。 |
| Validation reality-gap audit | 盤點現有 tests / artifacts / smoke 的 claim boundary，補上 human-observable product smoke，避免 dashboard PASS 但實機 workflow 仍不可用。 |
| Data Import UX alignment | task-oriented step-panel wizard baseline 和第一輪 task-panel visual polish 已交付；後續不再以 debug-style preview 為目標。 |
| BackendFacade boundary | Product runtime packages and product-success tests use `get_application_service(study)` / `ApplicationService`; `BackendFacade` is legacy compatibility only. |
| Architecture guard | 新增或維持 guard，防止 product runtime 和 product-success tests 繞過 command spine。 |
| Docs alignment | `current`、`roadmap`、`architecture` 不互相矛盾。 |

2026-05-12 狀態：backend command spine cleanup 已補上 product-success `BackendFacade`
guard、ApplicationService real-data / pipeline replacement coverage、dataset split default
regression、agent stage snapshot cleanup、full type/lint/docs/dashboard PASS。Epoch UI freeze/hang
reality gap 也已補上 command-backed real-GDF offscreen smoke：A01T/A02T/A03T epoching 回到 UI、
不開 blocking success modal，且 epoched preview 會取消 queued plot redraw。下一個不能跳過的
缺口仍是更完整的 human-observable desktop product smoke；不能用 dashboard PASS 或單一 offscreen
smoke 取代。

## 接下來才做

| Phase | 開始條件 |
| --- | --- |
| 1B Data Interpretation MVP Slice | downstream supervised-limited state、event extraction summary、metadata recipe provenance 和 screenshot artifact 補齊。 |
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
