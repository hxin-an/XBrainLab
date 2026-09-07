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

## Following work — parallel after the first slice

- Product Assistant architecture, golden-set language consistency and code organization.
- Backend/tests/frontend overdesign and legacy-path review, including noisy logs and preprocess latency.
  Repeated `Adding metadata with 1 columns` is reported noise, not yet a diagnosed cause of latency.
- Split work by non-overlapping ownership with concrete outputs; coordinate shared interfaces before edits.
  Independently review high-risk findings. Scope repairs from evidence, not an unrestricted rewrite.
- Experimental dataset/evaluator construction follows these two tracks, then Agent experiments.

## Source of truth

Git main and PRs own versions and approvals; docs/current.md owns product claims.
Keep pending work and actual decision/resource gaps here, not completed implementation history.
