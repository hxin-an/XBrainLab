# XBrainLab Agent Operations

最後更新：`2026-08-14`

`.agents/` 只保存 repo-local capability 與可重用流程。Repo 授權、scope、safety、complexity 與
handoff 不變量以 `AGENTS.md` 為唯一權威；這裡不複製清單或 current product truth。

## Progressive loading

1. 先讀 `AGENTS.md` 與任務直接涉及的 canonical source。
2. 只載入一個 primary skill；跨領域真有必要時最多一個 secondary。
3. 只有三步以上、需要 rollback 或 handoff 的任務才載入 workflow。
4. Thesis/tool-call claim 才讀 `.agents/context/thesis.md`；MCP 只在使用者明確要求時載入。

## Skills

| Scope | Skill |
| --- | --- |
| Assistant tools/contracts | `agent-toolcall-designer` |
| Architecture boundary | `architecture-reviewer` |
| Changed-code review | `code-reviewer` |
| EEG import/labels/BIDS | `data-interpretation-reviewer` |
| Canonical docs | `docs-curator` |
| MkDocs product UX | `docs-site-product-designer` |
| Explicit MCP | `mcp-adapter-reviewer` |
| Performance/resources | `performance-resource-reviewer` |
| Bounded refactor | `refactor-slicer` |
| Release/packaging | `release-packaging-reviewer` |
| Security/privacy | `security-privacy-reviewer` |
| Test-first change | `tdd-guard` |
| Test evidence quality | `test-quality-reviewer` |
| Thesis evidence | `thesis-evidence-reviewer` |
| Desktop UI review | `ui-product-reviewer` |
| Validation selection | `validation-runner` |

Skill frontmatter 是 routing authority；body 只定義專業方法與邊界。Reviewer finding 不授權實作，
也不會自動擴大 root scope ceiling。

## Workflows

| Workflow | Use |
| --- | --- |
| `architecture-review.md` | 將 current/target gap 收斂為一個可交付 slice。 |
| `documentation-review.md` | 合併 conflicting authority 與修復 links。 |
| `docs-site-redesign.md` | 已取得 UI/docs-site 授權後調整 portal。 |
| `refactor-slice.md` | 執行一個 behavior-preserving slice 後停止。 |
| `tdd-change.md` | Bug/core behavior 的 red-green loop。 |
| `test-audit.md` | 評估測試是否能抓到真實 defect。 |
| `agent-toolcall-scoring.md` | 產品穩定後的 tool-call experiment。 |
| `handoff-candidate.md` | 宣稱可手測／handoff-ready 前的完整 gate。 |

## Model dispatch

- 例行 status/docs/read-only review 或單一檔小修正：`gpt-5.6-terra` / `medium`。
- 複雜但 bounded 的 implementation、data integrity、security 或跨 owner 分析：`gpt-5.6-sol` / `high`。
- `xhigh` 只在使用者明確要求，或代表性任務已量測到收益時使用。Reasoning effort 只改變
  分析深度，不改變授權、scope 或 completion semantics。

這是後續 worker/eval dispatch policy，無法改變已啟動 session 的 host model。不以未量測的大量
A/B 作為 guidance merge gate。

## Retired surfaces

舊 stack/runbooks、superseded goals/branches、`Prep Gate`、`Repair Loop`、`AQ-*`、retired skills 和
`.agents/legacy/*` 只能作 historical token，不得 dispatch。
