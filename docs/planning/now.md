# XBrainLab Now

最後更新：`2026-09-07`

## Active — #115 Filter handoff, then #116

- User approved the Filter presentation scope: borders identify each toggle's section; Off dims its
  title, labels and controls while the toggle remains usable. Existing values, defaults, validation
  and backend filtering behavior must stay unchanged; no unrelated screen redesign.
- The existing #115 implementation is being integrated with current main. Review the merged diff,
  run focused Filter state/value and capture-inventory tests, inspect changed screenshots, then
  verify all applicable same-head CI including default visual comparison and Windows DPI evidence.
- Assumption: the existing Windows environment can be reused if dependency files are unchanged.
  Deliver the exact-source Windows app with a visible live-log console after engineering gates pass.
  Stop for manual acceptance; do not merge this product PR without the user's approval.
- Manual focus: all four toggle combinations, retained custom frequencies, Custom Notch fitting,
  Cancel/OK, and applying enabled filters. Offscreen evidence does not replace Windows acceptance.
- Next review #116 test pruning. #116 can use the approved
  non-product pre-merge notice rule only if review confirms no product behavior change or lost
  necessary protection. #115 remains a product manual-acceptance path.
- Preserve local settings.json and unrelated split UI/test edits; do not replace the running app
  unless requested. Resolve branch/worktree and approvals from Git/PR, not historical chat.
- Further SHA/full-data scan/copy cleanup remains a later candidate, not authorization to expand this
  Filter presentation slice. Earlier Windows native teardown and CI timeout causes were not proven
  fixed merely by later passing runs; retained evidence belongs in the relevant PRs.
- Existing bounded product Assistant acceptance remains valid within its documented limits.
  Unrelated product repairs do not trigger model promotion or a new model benchmark.

## Source of truth

Git main and PRs own versions and approvals; docs/current.md owns product claims.
Keep pending work and actual decision/resource gaps here, not completed implementation history.
