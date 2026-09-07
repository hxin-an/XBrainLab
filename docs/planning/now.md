# XBrainLab Now

最後更新：`2026-09-08`

## Active — CI quality wiring and scope correction (PR B)

- Audit confirmed missing actual Basedpyright/architecture/secrets CI, Ruff scope/version mismatch,
  and docs-workflow-only changes routed into product tests. Correct these without removing distinct
  regression/platform/native/data/UI evidence. Product behavior, new security tools and broad lint
  rewrites are out of scope. UI unchanged, no new manual acceptance required.
- Test routing/wiring first; add a shared locked-dependency quality job for existing analyzers and
  existing secrets checks, align Ruff, and document any existing lint debt without suppressing it.
  Keep baseline read-only and fail closed. Do not rerun full local product regression.
- Focused evidence: ci_change_scope/reliability tests, affected analyzer checks, YAML/static/docs;
  then independent review and exact-head applicable CI. User authorizes nonblocking notification,
  merge and immediate safe worktree/artifact cleanup after success.
- PR A #117 is separately in review/CI. Integrate it before publishing this branch so canonical tier
  guidance and the complete continuing Assistant plan are retained. Parent owns integration/PR/merge.

## Next — CI / validation rules and harness

- Reorganize useful retained checks by evidence, cost, duplication and failure diagnosis. Preserve
  historical debug timeout and macOS -11 failures: later passes did not establish their causes.
- Integrate the prepared native UI preview-first and context-compaction continuation guidance;
  audit structure without claiming identical fresh-agent behavior. Do not weaken gates, raise
  timeouts or silently skip failures to obtain green. Broad product cleanup remains out of scope.

## Source of truth

Git main and PRs own versions and approvals; docs/current.md owns product claims.
Keep pending work and actual decision/resource gaps here, not completed implementation history.
