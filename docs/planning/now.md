# XBrainLab Now

最後更新：`2026-09-07`

## Active — #114 Astra harness and fresh-session handoff

- User approved implementation of the official-docs-based harness plan. Quality priority is correctness
  and reliability, clear maintainable responsibilities, then removal of unnecessary complexity; no LOC,
  file-count, agent-count or reasoning-effort optimization target. No #114 merge authorization.
- Evidence: the old config inherited medium from Terra and its audit required that exact value. Old
  planning text retained completed work and conflicting dispatch; static checks did not establish that a
  fresh agent could load the right context or complete a real repair.
- Scope: integrate merged #113; reconcile repo instructions/skills/validation; remove forced reasoning
  defaults; verify native Codex discovery and fresh Astra behavior. No product Assistant/model change,
  global config/permission change, new control framework, or work on #115/#116.
- Steps: audit official Astra/Codex guidance and reachable repo instructions; preserve essential task
  context in its existing authority; update config/audit with focused red-green tests; run no-history
  takeover and validation-selection sessions plus an isolated replay of the known split-reopen defect.
  Check actual tool traces, source diffs and test output, not only the agent's summary. No hidden retries.
- Validation: guidance/schema tests, changed-script checks, strict docs builds, fresh-session evidence
  with actual model/config provenance, then same-head CI. Actual fresh sessions use existing account
  access and supported settings; unavailable required access is a blocker, not a simulated pass.
- UI: no product presentation change. The historical repair replay is authorized only in an isolated
  disposable checkout; no live app, product branch, external publication, or user settings mutation.
- Next: resolve the plan conflict, finish bounded instruction/config edits, then run fresh-session cases.

## Next — remaining PR review and computational cleanup

- #113 was manually accepted and merged on 2026-09-07. Exact source, CI and user approval remain in
  its PR; do not resume its historical repair plans. Earlier Windows native teardown failure had an
  unproven cause despite later successful gates; do not describe it as a separately diagnosed fix.
- Review #114 first, then #115 Filter and #116 test pruning; compare #111 with merged #113 before any
  decision to close it. No further PR merge approval is implied by #113 acceptance.
- Preserve local settings.json and unrelated split UI/test edits. Do not replace or monitor the user's
  running test app unless the current task requests it. Resolve worktree/branch/source identity from Git.
- After these PRs, consider repeated SHA/full-data scans/validation/copies using real call paths and
  measured costs. This is a candidate, not authorization to clean the whole product during #114.
- Existing bounded product Assistant acceptance remains valid within its documented limits; an
  unrelated desktop or harness task must not silently become Assistant promotion or model evaluation.

## Source of truth

Git main, remote refs and PRs own versions and approvals; docs/current.md owns current product claims.
Keep only pending work, decisions needed to continue and material limitations here. Completed task
history remains in Git/PR, not active dispatch. A new session must recheck external state before acting.
