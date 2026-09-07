# XBrainLab Now

最後更新：`2026-09-08`

## Active — #116 final test review and merge

- User authorized final review and merge of this tests-only slice without another approval prompt.
  Integrate current main, resolve only test conflicts, and retain the new split viewport, Epoch
  layout and shutdown concurrency protection. Do not change product source or widen pruning.
- Review each removed category against surviving observable behavior; independently check backend
  data/publication and architecture protection. Validate resolved tests, meaningful replacements,
  retained lifecycle behavior, architecture and static checks, then all same-head non-skipped CI.
- Notify before exact-head merge only after no blocking review findings and all checks pass.
  Preserve root settings.json, unrelated edits and the user's running app. No new hand test required
  unless the actual diff changes product behavior; stop for new scope/resource decisions if needed.

## Next — CI / validation rules and harness

- Reorganize useful retained checks by evidence, cost, duplication and failure diagnosis. Preserve
  historical debug timeout and macOS -11 failures: later passes did not establish their causes.
- Integrate the prepared native UI preview-first and context-compaction continuation guidance;
  audit structure without claiming identical fresh-agent behavior. Do not weaken gates, raise
  timeouts or silently skip failures to obtain green. Broad product cleanup remains out of scope.

## Source of truth

Git main and PRs own versions and approvals; docs/current.md owns product claims.
Keep pending work and actual decision/resource gaps here, not completed implementation history.
