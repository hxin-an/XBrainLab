# XBrainLab Now

最後更新：`2026-09-07`

## Active — finish #115; preserve the agreed UI; then #116 and CI cleanup

- User accepted Filter/Epoch design and requested completing #115 to manual testing. Freeze the
  visible design; no new UI features or broad saliency/backend cleanup. #111 is no longer active;
  verify source and merge state through Git/PR, not historical chat.
- #115's shutdown test oracle was corrected after a deterministic real-fence concurrency repro;
  no product lifecycle changed. Final same-head checks passed. Debug-domain timeout and prior
  macOS native exit -11 remain historical failures with unproven causes; later passes do not fix them.
- Outcome: focused defect evidence, same-head applicable successful CI, then launch the exact-source
  Windows app with visible log for manual acceptance. Product merge still needs user approval.
- Next: deliver the exact-source app and visible log, then await the user's full Filter/Epoch workflow
  acceptance and merge approval. Preserve unrelated local changes and running apps.
- Harness UI-preview and compaction-continuation rules are locally committed for the later guidance
  PR; structure checks passed, not new-agent behavioral proof. No global config or permissions changed.
- After #115, review #116 test pruning, then reorganize CI/validation around retained useful tests.
  The latter includes UI preview-first guidance; do not weaken gates to pass #115.

## Source of truth

Git main and PRs own versions and approvals; docs/current.md owns product claims.
Keep pending work and actual decision/resource gaps here, not completed implementation history.
