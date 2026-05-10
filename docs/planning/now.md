# XBrainLab Now

最後更新：`2026-05-10`

這頁只放下一輪施工焦點。

## 目前焦點

**Phase 1A：Backend Command Spine / Legacy / UI Refresh / Test Cleanup。**

要先做這件事，因為 MVP 前最大的風險不是功能不夠多，而是 UI、backend、assistant、MCP
各自保存一套 workflow truth。

## 本輪要達到

| 工作 | 完成判準 |
| --- | --- |
| Legacy product path cleanup | real `Study` runtime 的主要 mutating path 不再 silent fallback 到 legacy controller mutation。 |
| UI refresh cleanup | command 成功後的頁面更新由 shared refresh route / changed state 驅動，不由各頁自己猜。 |
| Test cleanup | 測試不再把 legacy fallback 當作預期成功路徑；mock 只隔離外部依賴。 |
| Validation reality-gap audit | 盤點現有 tests / artifacts / smoke 的 claim boundary，補上 human-observable product smoke，避免 dashboard PASS 但實機 workflow 仍不可用。 |
| BackendFacade boundary | `BackendFacade` 只包 `ApplicationService / Command API`，不重做 workflow logic。 |
| Architecture guard | 新增或維持 guard，防止 product path 繞過 command spine。 |
| Docs alignment | `current`、`roadmap`、`architecture` 不互相矛盾。 |

## 接下來才做

| Phase | 開始條件 |
| --- | --- |
| 1B Data Interpretation MVP Slice | Phase 1A 的 product path / refresh / test truth 收斂到可維護狀態。 |
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
