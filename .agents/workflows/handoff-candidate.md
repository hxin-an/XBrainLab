# Workflow: Handoff Candidate

最後更新：`2026-09-07`

For authorized delivery/merge, follow `docs/validation/README.md`; no duplicate local full manifest.

## 1. Scope and source

Check Git/PR identity and dirty ownership; preserve unrelated edits. Record behavior, protection and evidence gaps.

## 2. Focused local evidence

Visible design work first follows the validation contract's "UI design iteration before formal handoff"
section. A native design preview is an iteration endpoint, not a handoff-ready claim; enter formal
candidate validation after the user accepts the design.

Use the validation contract's L0–L3 tiers, not aggregate per-edit checks. Reproduce bugs/characterize
refactors; trace changed callers and record concrete risk before widening. Reuse equivalent CI evidence.

Visible changes need a changed-surface screenshot/walkthrough. Use widget state/geometry and existing
pixel comparison for machine-checkable facts. The primary agent reviews changed design and unexpected
differences, not every unchanged screenshot. Offscreen results do not replace Windows acceptance.

## 3. CI and specialized evidence

Use successful checks/artifacts for the same PR head instead of rerunning equivalent full tests,
builds or platform captures locally. Check exact source and all non-skipped conclusions with Git/GitHub
tools, not a model-generated PASS summary. Missing, pending, stale, cancelled or failed checks block
handoff-ready/manual-test delivery, not checkpoint reporting or independent authorized work.
A pass from another SHA/platform does not fill the gap.

Apply the validation contract's data/native/Assistant triggers; run specialized checks locally only if CI
lacks applicable evidence. Neither run the full manifest for unrelated changes nor call a reduced one complete.
When a full release dossier is explicitly needed, run the unmodified canonical manifest.

## 4. Delivery and continuation

After compaction, check plan, Git/PR and running sessions; execute the next unfinished step, not a
final recovery summary. Preserve endpoint, source/worktree, remaining work, evidence, session IDs
and blockers. Use commentary for progress; no duplicate work, new memory layer or expanded authority.

Report exact commit/PR, scoped changes, local/CI evidence and manual steps. Apply root completion labels;
desktop readiness can retain accepted Assistant limits, without promoting the Assistant to Stable.

`checkpoint` is a progress report, not a reason to end authorized work. Track the current PR through
pending CI using available wait/monitor tools with bounded waits and concise updates; do not require
another user prompt to resume. Continue useful independent authorized work while waiting, without
closing the user's app. Do not invent work or duplicate full validation just to remain busy.

On failed, cancelled, stale or missing checks, inspect actual evidence and complete safe in-scope
diagnosis/repair. Retry only when evidence supports it, preserving the original failure; do not increase
timeouts, weaken gates or expand product scope to get green. If necessary access, a new scope decision
or a user-only acceptance is genuinely missing, report what is blocked and the exact input needed.

Stop at the requested endpoint, a user pause, or a genuine resource/authority blocker, not simply at
commit, push or a status label. A request limited to review or opening a PR does not authorize merge.
For authorized merge, apply `docs/validation/README.md` approval rules: notify immediately beforehand
with PR/source, scope, checks and known limits; recheck base/head and gates, then use an exact-head
merge guard. The notice does not wait for a reply. Verify merge state before claiming completion.

## 5. Post-merge cleanup

After verifying merge, remove the PR worktrees and disposable builds, caches, CI downloads, logs and probes.
First retain required acceptance/failure evidence in its canonical location; resolve exact paths, source,
dirty state and active use. Use Git worktree removal and root process/deletion safety rules, never broad cleanup.
Preserve unmerged work, user settings, original data, durable results and shared/in-use environments;
do not put new shared environments in disposable worktrees. Report removed items, recoverability and retained
paths/reasons. Cleanup belongs to merge completion, not the next task; unexplained residue is not completion.
