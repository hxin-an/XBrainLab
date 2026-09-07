# XBrainLab Now

最後更新：`2026-09-08`

## Active — CI runner failure diagnosis (PR C)

- Existing shard runner kills timed-out children but does not explicitly request a pre-timeout stack;
  pytest/capture failures also skip several CI source-provenance steps. Historical debug timeout and
  macOS -11 roots remain unproven; this slice improves evidence, not an unsupported root-cause claim.
- Reuse stdlib/pytest fault diagnosis and current owned process cleanup. Keep exit/attestation checks
  fail closed. No new process owner/watchdog framework, raised timeout or automatic retry.
- Test first with real bounded child processes (hang/failure/early exit and successful cleanup), then
  implement minimal diagnostics and always-on post-execution provenance; preserve formal CI evidence.
  Limit edits to existing runners, directly related tests and CI diagnostic steps; no product/UI changes.
- Parent owns PR integration/review/CI/merge and will retain PR A's full continuing Assistant plan.
  Focused tests/static evidence only locally; exact-head CI before nonblocking merge notice and cleanup.

## Next — CI / validation rules and harness

- Reorganize useful retained checks by evidence, cost, duplication and failure diagnosis. Preserve
  historical debug timeout and macOS -11 failures: later passes did not establish their causes.
- Integrate the prepared native UI preview-first and context-compaction continuation guidance;
  audit structure without claiming identical fresh-agent behavior. Do not weaken gates, raise
  timeouts or silently skip failures to obtain green. Broad product cleanup remains out of scope.

## Source of truth

Git main and PRs own versions and approvals; docs/current.md owns product claims.
Keep pending work and actual decision/resource gaps here, not completed implementation history.
