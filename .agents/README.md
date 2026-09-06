# XBrainLab Agent Operations

最後更新：`2026-09-06`

`.agents/` 只保存 repo-local capability 與可重用流程。Repo 授權、scope、safety、complexity 與
handoff 不變量以 `AGENTS.md` 為唯一權威；這裡不複製清單或 current product truth。

## Progressive loading

1. 先讀 `AGENTS.md` 與任務直接涉及的 canonical source。
2. 使用者點名的 skill 必須載入；否則先載入處理目前 phase 所需的 primary skill，只有實際跨領域
   時才加入其他 skill。
3. 當某個 workflow 的程序治理目前工作時才載入它；不要以步數、skill 數或 routine task 強制載入。
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

`gpt-6-astra` / `medium` coordinates and reviews the task. `gpt-5.6-terra` / `medium` is the default
bounded worker; `gpt-5.6-luna` / `medium` fits repeatable work with an exact oracle. Use
`gpt-5.6-sol` only for a bounded deep review whose unresolved reasoning materially affects the current
scope. Model choice never changes authorization, scope, completion semantics, or the live product
Assistant model/revision; diagnose environment failures before changing a worker choice.

Delegate when the user requests coordination or two independent useful streams save time or improve evidence.
A single workflow of at most 8 production files normally stays with its owner. Use no more than the configured
worker cap and do not duplicate review dimensions. `xhigh` requires explicit
direction or measured benefit; bulk A/B is not a merge gate.

These are repo choices, not an official universal architecture. See the official [Astra model guidance](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#prompting-best-practices), [skills guidance](https://developers.openai.com/codex/skills), [subagent configuration](https://developers.openai.com/codex/multi-agent), and [config basics](https://learn.chatgpt.com/docs/config-file/config-basic).

## Retired surfaces

舊 stack/runbooks、superseded goals/branches、`Prep Gate`、`Repair Loop`、`AQ-*`、retired skills 和
`.agents/legacy/*` 只能作 historical token，不得 dispatch。
