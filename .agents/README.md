# XBrainLab Agent Operations

最後更新：`2026-08-14`

`.agents/` 只保存 repo-local capability 與可重用流程。Repo 授權、scope、safety、complexity 與
handoff 不變量以 `AGENTS.md` 為唯一權威；這裡不複製清單或 current product truth。

## Progressive loading

1. 先讀 `AGENTS.md` 與任務直接涉及的 canonical source。
2. 只載入一個 primary skill；跨領域真有必要時最多一個 secondary。
3. 只有三步以上、需要 rollback 或 handoff 的任務才載入 workflow。
4. Thesis/tool-call claim 才讀 `.agents/context/thesis.md`；已退役的MCP surface不再dispatch。

## Skills

| Scope | Skill |
| --- | --- |
| Assistant tools/contracts | `agent-toolcall-designer` |
| Architecture boundary | `architecture-reviewer` |
| Changed-code review | `code-reviewer` |
| EEG import/labels/BIDS | `data-interpretation-reviewer` |
| Canonical docs | `docs-curator` |
| MkDocs product UX | `docs-site-product-designer` |
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

`gpt-5.6-terra` / `medium` is coordinator and worker fallback. Delegated plans emit:
`Dispatch: coordinator; workers; Sol trigger; Fast; escalation`.

- `gpt-5.6-luna` / `medium` / Standard：repeatable single-owner work with an exact oracle.
  Tiny work stays with Terra when delegation would duplicate more context than it saves.
- Terra：bounded work using an existing owner/contract; use `high` for a difficult trace below Sol.
- `gpt-5.6-sol` / `high` only for: `S1` authority/contract conflict; `S2` owner/state-truth migration;
  `S3` novel safety/state/rollback/cancel protocol; `S4` inseparable coupled risks; `S5` valid designs with
  different public/failure semantics; `S6` scientific/thesis/tool-call evidence protocol design.
- LOC/files, keywords, unfamiliarity, red CI or deadline are not Sol triggers. Split broad work; return
  implementation to Terra/Luna after a Sol decision.
- Fast is foreground Luna only when the user waits on model generation. Background stays Standard; repo
  config never persists Fast or changes a host model.
- A cheaper model gets one complete attempt. Escalate for a demonstrated capability/understanding gap;
  diagnose tool, test, CI, download or environment failures without changing model.

`xhigh` requires explicit direction or measured benefit. No bulk A/B is a merge gate;
model choice never changes authorization, scope or completion semantics.

## Retired surfaces

舊 stack/runbooks、superseded goals/branches、`Prep Gate`、`Repair Loop`、`AQ-*`、retired skills 和
`.agents/legacy/*` 只能作 historical token，不得 dispatch。
