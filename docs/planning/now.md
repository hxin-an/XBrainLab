# XBrainLab Now

最後更新：`2026-09-07`

## Next — #111 manual-test candidate, then #115 / #116

- User requested finishing #111 against current main. Keep #113's no-auto-retry behavior: only the
  expected stale render error bypasses the generic worker ERROR and reuses the panel's existing
  unavailable/Refresh path. Unexpected errors, backend guards, selection/shutdown checks, UI copy and
  layout remain unchanged. The original retry-based #111 patch must not be restored.
- Implementation and independent lifecycle review are complete. Verify current PR/source and all
  applicable same-head CI before delivering the Windows manual-test candidate; exact tests, results
  and source belong in #111. Product merge requires new exact-source manual acceptance and approval.
- Manual focus: while training continues, open completed Evaluation results; refresh and change
  fold/run selections, close/reopen the panel. Expected stale reads must not emit Worker task failed;
  genuine failures must still be reported. Ordinary completed results and explicit Refresh must work.
- After #111, review #115 Filter presentation and #116 test pruning. #116 can use the approved
  non-product pre-merge notice rule only if review confirms no product behavior change or lost
  necessary protection. #115 remains a product manual-acceptance path.
- Preserve local settings.json and unrelated split UI/test edits; do not replace the running app
  unless requested. Resolve branch/worktree and approvals from Git/PR, not historical chat.
- Further SHA/full-data scan/copy cleanup remains a later candidate, not authorization to expand this
  Evaluation reporting slice. Earlier Windows native teardown and CI timeout causes were not proven
  fixed merely by later passing runs; retained evidence belongs in the relevant PRs.
- Existing bounded product Assistant acceptance remains valid within its documented limits.
  Unrelated product repairs do not trigger model promotion or a new model benchmark.

## Source of truth

Git main and PRs own versions and approvals; docs/current.md owns product claims.
Keep pending work and actual decision/resource gaps here, not completed implementation history.
