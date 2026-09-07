# XBrainLab Now

最後更新：`2026-09-07`

## Next — finish #114, then remaining PRs

- User approved the official-docs-based Astra harness implementation. The instruction/config changes
  are implemented. Resolve #114 state from Git/PR: if open, inspect its current candidate evidence and
  track through the authorized endpoint; if merged, proceed to the next queued PR. Apply the approved
  non-product pre-merge notice rule. Exact source, CI and fresh-session traces belong in the PR;
  checkpoint/pending CI is not a stopping condition.
- Quality priority: correctness/reliability, clear maintainable responsibilities, then removal of
  unnecessary complexity. Do not optimize toward minimum LOC/files/abstractions or a fixed agent count.
- Repo no longer fixes reasoning effort or worker model/effort. Check effective session settings and
  instruction/skill discovery; do not assume a config file proves runtime inheritance.
- User approved adaptive delegation and risk-based independent review, not a fixed worker cap or role
  quota. Config/audit and guidance now follow that decision; criteria live in `.agents/README.md`.
- Previous #114 CI timed out in the Linux integration-rest path (exit 124), leaving incomplete shard
  provenance. Preserve the failed run in the PR; check new-source CI before readiness. This is not an
  accepted imperfect model score, and its underlying cause is not yet diagnosed. Do not expand this
  harness slice into product/test repairs or increase timeouts to bypass it.
- Harness acceptance needs no-history takeover/validation selection and an isolated real-repair replay.
  Read actual tool events, test exits and diff; static audit or an agent summary alone is insufficient.
  A replay uses an intentionally modified isolated fixture, not the live product or a new product PR.
- #113 was manually accepted and merged on 2026-09-07. Its exact source and approval remain in its PR;
  do not resume its historical repair plans. Earlier Windows native teardown failure had an unproven
  cause despite later successful gates; do not claim a separately diagnosed fix.
- Review #115 Filter and #116 test pruning after #114; compare #111 with merged #113 before deciding
  whether to close it. Product PRs still require their own manual acceptance and merge approval.
- Preserve local settings.json and unrelated split UI/test edits. Do not replace or monitor the user's
  running test app unless requested. Resolve worktree/branch/source identity from Git.
- After these PRs, consider repeated SHA/full-data scans/validation/copies using real call paths and
  measured costs. This candidate is not authorization for whole-product cleanup during harness work.
- Existing bounded product Assistant acceptance remains valid within its documented limits; unrelated
  desktop/harness work must not silently become Assistant promotion or model evaluation.

## Source of truth

Git main, remote refs and PRs own versions and approvals; docs/current.md owns current product claims.
Keep pending work, decisions needed to continue and material limitations here. Completed task history
remains in Git/PR, not active dispatch. New sessions must recheck external state before acting.
