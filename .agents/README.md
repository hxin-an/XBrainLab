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
| `refactor-slice.md` | 執行一個 behavior-preserving slice 後停止。 |
| `tdd-change.md` | Bug/core behavior 的 red-green loop。 |
| `test-audit.md` | 評估測試是否能抓到真實 defect。 |
| `agent-toolcall-scoring.md` | 產品穩定後的 tool-call experiment。 |
| `handoff-candidate.md` | Focused evidence 與同版本 CI 的交付判定。 |

## Model dispatch

The project defaults to `gpt-6-astra`. Leave reasoning effort and worker model/effort unset in repo
config: the active user/session effort applies, and workers inherit their parent. Do not silently
change model/effort when delegating. Verify effective settings at launch; repo text is not proof of
runtime configuration. This does not change the product Assistant or grant API/download authority.

Delegate when the user requests coordination or two independent useful streams save time or improve evidence.
A small coherent task may stay with its owner. Cap concurrent subagent
threads at 2 (coordinator excluded); isolate writes and return concise evidence, not duplicate reviews.
Pending CI or manual acceptance does not pause independent authorized work.

Use deterministic commands for Git/CI identity, counts, schemas, widget visibility/enabled state,
geometry and pixel differences. Read summaries and failure details, not whole successful logs.
Use model review for meaning, design and unexplained differences; no routine VLM pass over unchanged
screenshots. See the validation contract for evidence selection and reuse.

## Official basis and fresh sessions

Reviewed 2026-09-07: [Astra prompting](https://developers.openai.com/api/docs/guides/latest-model#prompting-best-practices)
motivates explicit follow-through, conflict auditing, useful delegation and proportionate testing.
[AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[skills](https://learn.chatgpt.com/docs/build-skills), [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
and [config precedence](https://learn.chatgpt.com/docs/config-file/config-basic) define native loading.
These support the mechanisms, not a universal best architecture or a preferred reasoning effort.

Start a fresh session in the intended trusted checkout. Check its effective model/effort, instruction
sources and skill discovery; user/global/nested overrides can change behavior. Do not edit global
config or relax permissions to make a test pass. If required context is absent, report the actual gap.
Acceptance of harness changes includes no-history task takeover and real behavior evidence as defined
in the validation contract, not just successful parsing or the model repeating these instructions.
