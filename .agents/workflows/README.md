# XBrainLab Agent Workflows

最後更新：`2026-05-02`

workflow 是「多步驟流程」。它可以引用 `.agents/skills/`，但不取代 canonical docs。

## Active Workflows

| Workflow | 用途 |
| --- | --- |
| `tdd-change.md` | test-first bug fix / 小型行為變更。 |
| `test-audit.md` | 審視測試品質、mock-heavy 風險與 missing evidence。 |
| `documentation-review.md` | 文件整理與 canonical 化。 |
| `architecture-review.md` | 架構複盤與 product-delivery 順序校準。 |
| `refactor-slice.md` | 選定並執行第一個重構 slice。 |
| `agent-toolcall-scoring.md` | 設計 tool-call scoring system。 |

## 使用原則

- substantial work 前先選 workflow；product-delivery 任務不必被純 review workflow 擋住。
- workflow 執行中若發現 target / current / validation 衝突，先修文件或回報使用者，不直接硬做。
- workflow 結束時要留下驗證結果與 worklog。
