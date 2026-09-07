# XBrainLab Now

最後更新：`2026-09-08`

## Active — CI, validation and harness cleanup

- #115 and #116 are merged (verified through GitHub). Next, consolidate CI/validation and the pending
  UI-preview, compaction-continuation and post-merge cleanup guidance. No product UI change is authorized
  by this guidance slice. Preserve dirty root/replay work and the unmerged guidance branch.
- Inspect historical debug-domain timeout and macOS native exit -11 evidence; causes remain unproven.
  Later passes are not fixes. Select deterministic, relevant checks and reuse same-source CI evidence;
  do not weaken gates, duplicate heavy local runs or claim fresh-agent behavior from parsing alone.
- Outcome: L0/L1 fast local feedback, L2 same-head CI and L3 explicit dossiers; never run aggregates
  per edit. Execute three bounded PRs: A guidance/entrypoint clarity, B Ruff/type/architecture CI wiring,
  C runner failure diagnostics. Next: finish A review, focused guidance/docs evidence and same-head CI.
- Review every CI job's trigger, observable protection, duplication and gaps. Remove only demonstrated
  redundancy/unneeded routing while preserving required evidence; add missing meaningful gates, not
  more checks by default. No failure hiding through skips or timeout increases.
- User authorized independent-reviewed non-product PRs to merge after a notice without waiting for
  a reply. Clean each merged worktree/output, then continue through Assistant manual-test delivery.
  Commit, pending CI and compaction are not endpoints. Product PRs still require manual acceptance.

## Execution and validation adequacy

- Inspect CI routing, runner timeout/crash evidence and representative low-mock lifecycle tests before
  changing gates. Map claims to actual production entry points, transitions and observable side effects.
- Classify protection as demonstrated, weak/duplicated, or missing; passing totals and static checks
  alone do not establish workflow readiness. Add only directly justified protection in this slice;
  wider product/test repairs belong to the following workflow audit.
- Focused validation: guidance/reference audit and strict docs build; changed CI/runner contract tests,
  including real subprocess failure/timeout behavior if that boundary changes; same-head applicable CI.
- Non-goals: product UI/runtime changes, model/evaluator redesign, broader test deletion, new control
  frameworks, timeout increases or automatic retries that hide failures. No UI approval needed here.

## Following work — agreed order

- Before Assistant changes, repair the existing evaluator/exporter to use production RAG lifecycle,
  retrieval/tool filtering, assembler and local template/budget path. Current case projection bypasses
  RAG. Establish a RAG-enabled pre-change baseline; historical no-RAG scores are not directly comparable.
- Freeze model/revision, cases/scorer/denominator and tool/confirmation/publication contracts. Capture
  retrieval identity/order, inclusion/drop/failure, final prompt, raw/Host/product outcomes and latency.
  No evaluator expected answer may select examples; disclose corpus/case overlap and degraded RAG.
- Then clean Assistant architecture and inspect actual assembled and final rendered prompts including
  real RAG/history/retry/clarification. User authorizes prompt wording/structure/examples improvements,
  not UI, tool/permission changes or blanket Chinese deletion. Separate refactor and semantic commits.
- Assistant support and acceptance are English-only. Do not add Chinese capability or multilingual
  gates; classify existing non-English material by real role/callers before cleanup.
- Respect the small models' current input/output budgets; assess short/medium/near-limit cases and
  optional-context removal. No context inflation or new summary model. Use focused cases during edits,
  applicable frozen bounded evidence on the final candidate, without requiring unaccepted Stable scores.
- Independent review plus same-head applicable CI precedes the Assistant product PR/manual delivery.
  Open exact-source native app with visible log, confirm responsive, then hand over without prolonged
  monitoring. Necessary unavailable resources/new contract decisions are genuine blockers; isolate them
  and continue independent work. Do not start new research datasets/evaluators in this run.
- In parallel with Assistant organization, investigate noisy logs and preprocess latency.
  Repeated `Adding metadata with 1 columns` is reported noise, not yet a diagnosed cause of latency.
- Split work by non-overlapping ownership with concrete outputs; coordinate shared interfaces before edits.
  Independently review high-risk findings. Scope repairs from evidence, not an unrestricted rewrite.
- After those tracks, audit frontend → backend → tests in parallel by user workflow: data preparation,
  training, and result presentation. Inspect repeated calculation/validation, SHA, caches, state owners,
  compatibility branches, async lifecycle and high-mock protection. Classify findings as must-fix,
  worthwhile simplification or justified retention; implement bounded PRs, not a wholesale rewrite.
- Experimental dataset/evaluator construction follows the workflow audit, then Agent experiments.

## Source of truth

Git main and PRs own versions and approvals; docs/current.md owns product claims.
Keep pending work and actual decision/resource gaps here, not completed implementation history.
