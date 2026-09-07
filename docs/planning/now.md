# XBrainLab Now

最後更新：`2026-09-07`

## Next — #114 review, then remaining PRs

- User approved the official-docs-based Astra harness implementation. The instruction/config changes
  are implemented; review #114 against current main and inspect its current candidate evidence before
  acceptance. No #114 merge authorization. Exact source, CI and fresh-session traces belong in the PR.
- Quality priority: correctness/reliability, clear maintainable responsibilities, then removal of
  unnecessary complexity. Do not optimize toward minimum LOC/files/abstractions or a fixed agent count.
- Repo no longer fixes reasoning effort or worker model/effort. Check effective session settings and
  instruction/skill discovery; do not assume a config file proves runtime inheritance.
- Harness acceptance needs no-history takeover/validation selection and an isolated real-repair replay.
  Read actual tool events, test exits and diff; static audit or an agent summary alone is insufficient.
  A replay uses an intentionally modified isolated fixture, not the live product or a new product PR.
- #113 was manually accepted and merged on 2026-09-07. Its exact source and approval remain in its PR;
  do not resume its historical repair plans. Earlier Windows native teardown failure had an unproven
  cause despite later successful gates; do not claim a separately diagnosed fix.
- Review #115 Filter and #116 test pruning after #114; compare #111 with merged #113 before deciding
  whether to close it. No subsequent PR merge approval is implied by #113 acceptance.
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
