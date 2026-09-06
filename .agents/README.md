# XBrainLab Agent Operations

最後更新：`2026-09-07`

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
| `handoff-candidate.md` | Focused evidence 與同版本 CI 的交付判定。 |

## Model dispatch

`gpt-6-astra` / `medium` is the coordinator and worker default. All development agents use Astra;
do not route simple work to another model or silently fall back. Explicit session reasoning choices
remain effective; a difficult task does not itself authorize changing them. This configuration does
not change the product Assistant model/revision or grant API/download authority.

Delegate when the user requests coordination or two independent useful streams save time or improve evidence.
A single workflow of at most 8 production files normally stays with its owner. Cap concurrent subagent
threads at 2 (coordinator excluded); isolate writes and return concise evidence, not duplicate reviews.
Pending CI or manual acceptance does not pause independent authorized work.

Use deterministic commands for Git/CI identity, counts, schemas, widget visibility/enabled state,
geometry and pixel differences. Read summaries and failure details, not whole successful logs.
Use model review for meaning, design and unexplained differences; no routine VLM pass over unchanged
screenshots. See the validation contract for evidence selection and reuse.

These are repo choices, not an official universal architecture. See the official [Astra model guidance](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#prompting-best-practices), [skills guidance](https://developers.openai.com/codex/skills), [subagent configuration](https://developers.openai.com/codex/multi-agent), and [config basics](https://learn.chatgpt.com/docs/config-file/config-basic).
