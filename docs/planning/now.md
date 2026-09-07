# XBrainLab Now

最後更新：`2026-09-07`

## Active — #115 Filter / Epoch handoff, then #116

- User accepted the revised native Filter and Epoch design: subtle consistent cards, shared native
  switches, readable disabled-section titles, compact title/subtitle spacing and content-fitted height.
  Preserve all filtering, event, window, confirmation and baseline-validation behavior.
- Design iteration is complete. Review the final diff and focused tests, update only the reviewed
  Filter references, and verify all applicable same-head CI including default visual, Windows DPI
  and source-diverse dataset evidence. Capture fixtures must use the real content-fitted Epoch size.
- Deliver the exact-source Windows application with visible live logs after engineering gates pass.
  Native design previews used example labels and are not full workflow/manual merge acceptance.
  User approval to merge #115 is still required; prior-head CI cannot certify the revised source.
- UI work uses direct native previews for CLI users, focused interaction checks during iteration,
  then heavy CI/platform/DPI validation after design acceptance. Do not replace the user's main app
  while iterating previews; close only identifiable agent-owned preview processes.
- Manual focus: Filter combinations/custom values/apply; Epoch title spacing, compact height,
  consistent Import card, baseline toggles/errors and completed epoch creation on familiar data.
  No unrelated UI redesign, data semantics change or Assistant benchmark/promotion work.
- Next review #116 test pruning against latest main. Non-product pre-merge notice applies only after
  confirming no product behavior change or lost necessary protection and all same-head gates pass.
- Preserve root settings.json and unrelated split UI/test edits. Git/PR own source and approvals.
  Further SHA/full-data scan/copy cleanup remains a later candidate, outside this slice.

## Source of truth

Git main and PRs own versions and approvals; docs/current.md owns product claims.
Keep pending work and actual decision/resource gaps here, not completed implementation history.
