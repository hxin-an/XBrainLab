# XBrainLab Now

最後更新：`2026-09-08`

## Active — CI, validation and harness cleanup

- #115 and #116 are merged (verified through GitHub). Next, consolidate CI/validation and the pending
  UI-preview, compaction-continuation and post-merge cleanup guidance. No product UI change is authorized
  by this guidance slice. Preserve dirty root/replay work and the unmerged guidance branch.
- Inspect historical debug-domain timeout and macOS native exit -11 evidence; causes remain unproven.
  Later passes are not fixes. Select deterministic, relevant checks and reuse same-source CI evidence;
  do not weaken gates, duplicate heavy local runs or claim fresh-agent behavior from parsing alone.
- Outcome: clear validation ownership, useful gates and a sustainable merge/cleanup workflow.
  Before CI implementation, bound the observed failures, affected files and focused checks. Stop when
  the authorized guidance/CI slice has its required evidence and merge/cleanup endpoint, or a genuine blocker.

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

- Product Assistant architecture, golden-set language consistency and code organization.
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
