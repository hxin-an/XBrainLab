# XBrainLab Agent Operations

最後更新：`2026-08-11`

`.agents/` 只保存 repo-local agent 能力與可重用流程，不保存產品 current truth、active branch、
gate argv 或 finding queue。一般入口先讀根目錄 `AGENTS.md`；只有任務命中時才載入相應 skill
或 workflow。

## 唯一權威

| 問題 | 唯一入口 |
| --- | --- |
| Repo 級安全、授權、dirty/branch、handoff 不變量 | `AGENTS.md` |
| Current product/candidate truth | `docs/current.md`、`docs/planning/now.md` |
| Current / target architecture | `docs/architecture/`、`docs/target/` |
| Claim/evidence 解讀 | `docs/validation/README.md` |
| Executable handoff gate IDs 與 argv | `scripts/dev/handoff_gate_spec.py` |
| Skill routing | 各 `.agents/skills/*/SKILL.md` frontmatter |
| 多步驟 agent 流程 | `.agents/workflows/*.md` |
| 歷史與 provenance | `docs/records/`、Git history |

若入口衝突，以 source/runtime/Git evidence 校準 canonical docs；不要讓 skill、workflow 或 record
成為第二份 current truth。

## Progressive loading

1. 先讀 `AGENTS.md` 與任務直接涉及的 canonical docs。
2. 只載入一個 primary skill；跨領域確有需要時才加入 secondary skill。
3. Skill body 只定義方法與邊界；其中引用的文件也只在當前步驟需要時讀。
4. Workflow 用於三步以上或需要明確 handoff/rollback 的流程，不因名稱相似而全部載入。
5. 論文與 tool-call claim 才讀 `.agents/context/thesis.md`。
6. `mcp-adapter-reviewer` 只能由使用者明確點名或明確要求 MCP 工作時載入。

## Skills

| Primary scope | Skill | Boundary |
| --- | --- | --- |
| Assistant tools/contracts | `agent-toolcall-designer` | Tool/state/verification surface；不是一般架構 review。 |
| Architecture | `architecture-reviewer` | Current vs target boundaries；不是 line-level diff review。 |
| Code changes | `code-reviewer` | Regression、lifecycle、maintainability、architecture drift。 |
| EEG data semantics | `data-interpretation-reviewer` | Import、events、labels、BIDS、recipe/capability。 |
| Canonical docs | `docs-curator` | Current/target/planning/records 分工與連結。 |
| Docs portal UX | `docs-site-product-designer` | MkDocs IA、visual hierarchy、artifact gallery。 |
| Explicit MCP | `mcp-adapter-reviewer` | Explicit-only historical adapter scope。 |
| Performance/resources | `performance-resource-reviewer` | Measurement、memory/GPU/cache、responsiveness。 |
| Refactor slicing | `refactor-slicer` | Bounded slice、call sites、rollback、validation。 |
| Release/packaging | `release-packaging-reviewer` | Launcher、packaging、platform acceptance。 |
| Security/privacy | `security-privacy-reviewer` | Data、files、LLM、agency、logs、secrets。 |
| Test-first change | `tdd-guard` | Bug/core behavior loop and characterization baseline。 |
| Test evidence | `test-quality-reviewer` | Test strength、mock risk、claim boundary。 |
| Thesis evidence | `thesis-evidence-reviewer` | Exact model/cases/scorer/reproducibility。 |
| UI product quality | `ui-product-reviewer` | Desktop workflow、copy、states、visual artifacts。 |
| Validation | `validation-runner` | Select/execute/interpret canonical gates。 |

`clean-code-reviewer` 已合併進 `code-reviewer`；`software-design-reviewer` 已合併進
`architecture-reviewer`；branch/PR 穩定規則在根 `AGENTS.md`，具體 handoff 流程在
`workflows/handoff-candidate.md`。不要恢復這三個退役 skills。

## Workflows

| Workflow | Use |
| --- | --- |
| `architecture-review.md` | 盤點 current/target gap 並排序可交付 slice。 |
| `documentation-review.md` | 找 current truth split、stale link 與 record leakage。 |
| `docs-site-redesign.md` | 重整 MkDocs portal 並以 screenshots review。 |
| `refactor-slice.md` | 將 backend/UI/Assistant refactor 切成可驗證步驟。 |
| `tdd-change.md` | 進行 bug/core behavior test-first loop。 |
| `test-audit.md` | 分類 strong/weak tests 並補 evidence。 |
| `agent-toolcall-scoring.md` | 產品穩定後建立 tool-call experiment。 |
| `handoff-candidate.md` | 宣稱可手測/handoff-ready 前的完整 gate。 |

## Bounded delivery loop

1. 從 Git、source 與 canonical docs 定義 scope/non-goals。
2. 找同類 call sites、observable behavior 與最低 evidence。
3. Bug 先重現；純重構先建立 passing characterization baseline。
4. 實作最小 coherent slice，不引入第二份 workflow truth。
5. 跑 focused test、same-class guard 與相鄰 regression。
6. 將重要決策、current truth、validation boundary 寫回相應 canonical docs。
7. Review diff、dirty state、artifact 與 claim boundary；再 commit/push/PR。

Refactor slice 至少記錄 scope、call sites、target boundary、affected files、validation 與 rollback。
UI-only refactor 不強迫使用 command-shape template；涉及 state-changing workflow 時才需要 command/
service contract。Validation 未覆蓋完整 declared scope 時只能稱 checkpoint。

## Retired control surfaces

下列內容只能作歷史字詞或 migration guard，不得 dispatch：

- superseded product-closure goal files and stabilization branches
- `Prep Gate`、`Repair Loop`、`AQ-*`
- retired runbook/stack layers and duplicate skill/workflow indexes
- `docs/current/*`、`docs/history/*`、`docs/workflows/*`、`.agents/legacy/*`

需要歷史理由時查 Git history 或明確標成 historical 的 record；不要把它們重新加入先讀清單。
