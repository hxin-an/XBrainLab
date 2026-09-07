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

Skill names/descriptions in the discovered `.agents/skills/` catalog own task routing; select by actual
scope. This index does not duplicate that catalog or require a reviewer for every domain mentioned.

## Workflows

| Workflow | Use |
| --- | --- |
| `architecture-review.md` | 將 current/target gap 收斂為一個可交付 slice。 |
| `documentation-review.md` | 合併 conflicting authority 與修復 links。 |
| `docs-site-redesign.md` | 已取得 UI/docs-site 授權後調整 portal。 |
| `refactor-slice.md` | 分段重構並完成已授權 outcome。 |
| `tdd-change.md` | Bug/core behavior 的 red-green loop。 |
| `test-audit.md` | 評估測試是否能抓到真實 defect。 |
| `agent-toolcall-scoring.md` | 產品穩定後的 tool-call experiment。 |
| `handoff-candidate.md` | Focused evidence 與同版本 CI 的交付判定。 |

## Model dispatch

Default to `gpt-6-astra`; leave repo effort and worker model/effort unset to inherit session/parent
settings. No silent fallback. Verify effective settings at launch. Product Assistant is unchanged.

## Delegation and review

Delegate when a bounded task has clear inputs, independently verifiable output and useful work that
can proceed alongside the main task. Expected time or evidence gains must outweigh coordination,
resource and conflict costs. Keep write ownership separate; regroup when dependencies or overlap arise.
Small coherent changes can stay local. No repo headcount/role quota; respect runtime resource limits.
The main agent may implement and must inspect actual diffs/evidence before integrating results.

Review every change against its requirement, diff and meaningful tests. Use independent review for
high-risk lifecycle/data/publication boundaries, cross-owner changes or repeatedly failed repairs.
Give the reviewer a concrete risk question; do not duplicate broad reviews or use review as a substitute
for real tests. See `skills/code-reviewer/SKILL.md` for findings. Pending CI/manual acceptance does not
pause independent authorized work.

Use deterministic commands for Git/CI identity, counts, schemas, widget visibility/enabled state,
geometry and pixel differences. Read summaries and failure details, not whole successful logs.
Use model review for meaning, design and unexplained differences; no routine VLM pass over unchanged
screenshots. See the validation contract for evidence selection and reuse.

## Official basis and fresh sessions

Reviewed 2026-09-07: [Astra guidance](https://developers.openai.com/api/docs/guides/latest-model),
[instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[skills](https://learn.chatgpt.com/docs/build-skills) and
[subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
Official mechanisms inform these repo choices, not a universal architecture or preferred effort.

In a fresh trusted checkout session, verify model/effort and instruction/skill discovery; disclose
global/nested overrides and missing context without changing global config or permissions.
Use the validation contract's no-history takeover and real-behavior evidence, not parsing alone.
