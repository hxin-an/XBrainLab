# XBrainLab Now

最後更新：`2026-09-07`

## Active — finish #115; preserve the agreed UI; then #116 and CI cleanup

- User accepted Filter/Epoch design and requested completing #115 to manual testing. Freeze the
  visible design; no new UI features or broad saliency/backend cleanup. #111 is no longer active;
  verify source and merge state through Git/PR, not historical chat.
- #115 same-head CI reported a shutdown callback lock-availability assertion failure and a debug
  domain timeout. Diagnose actual failures before repair or evidence-backed rerun; a passing local
  run does not erase them. Prior macOS native exit -11 remains an unproven historical failure.
- Outcome: focused defect evidence, same-head applicable successful CI, then launch the exact-source
  Windows app with visible log for manual acceptance. Product merge still needs user approval.
- Harness: persist context-compaction continuation in root guidance, using existing plan/session
  mechanisms only. Validate guidance structure; do not claim new-agent behavioral proof from audits.
- Next: inspect the failing test/lifecycle boundaries, isolate any minimal necessary repair and rerun
  focused protection. Stop only at manual delivery or a genuine decision/resource gap; preserve all
  unrelated local changes and running apps.
- After #115, review #116 test pruning, then reorganize CI/validation around retained useful tests.
  The latter includes UI preview-first guidance; do not weaken gates to pass #115.

## Source of truth

Git main and PRs own versions and approvals; docs/current.md owns product claims.
Keep pending work and actual decision/resource gaps here, not completed implementation history.
