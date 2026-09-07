# Workflow: Handoff Candidate

最後更新：`2026-09-07`

Use when delivering or merging an authorized PR. Follow the evidence selection in
`docs/validation/README.md`; an ordinary PR does not require a duplicate local full manifest.

## 1. Scope and source

Read Git branch, HEAD, upstream, dirty ownership and the actual PR base/head. Preserve unrelated edits.
Record the changed behavior, focused protection and what remains unverified in the PR.

## 2. Focused local evidence

Visible design work first follows the validation contract's "UI design iteration before formal handoff"
section. A native design preview is an iteration endpoint, not a handoff-ready claim; enter formal
candidate validation after the user accepts the design.

For a bug, reproduce the observable failure then rerun the protection after repair. For a refactor,
use a passing characterization baseline. Trace the directly changed lifecycle and callers.
Run only the relevant tests/static checks; widen when changed code, failures or unresolved risk justify it.

Visible changes need a changed-surface screenshot/walkthrough. Use widget state/geometry and existing
pixel comparison for machine-checkable facts. The primary agent reviews changed design and unexpected
differences, not every unchanged screenshot. Offscreen results do not replace Windows acceptance.

## 3. CI and specialized evidence

Use successful checks/artifacts for the same PR head instead of rerunning equivalent full tests,
builds or platform captures locally. Check exact source and all non-skipped conclusions with Git/GitHub
tools, not a model-generated PASS summary. Missing, pending, stale, cancelled or failed checks block
handoff-ready/manual-test delivery, not checkpoint reporting or independent authorized work.
A pass from another SHA/platform does not fill the gap.

Apply the canonical validation contract's data, native lifecycle and Assistant evidence triggers.
Run local specialized checks only when applicable evidence is absent from CI. Do not execute the full
manifest for a small unrelated change, or invent a reduced manifest and call it complete.
When a full release dossier is explicitly needed, run the unmodified canonical manifest.

## 4. Delivery and continuation

Report exact commit/PR, scoped changes, local checks, CI/artifact evidence and manual steps. Use:
- `handoff-ready` when all applicable evidence is complete.
- `checkpoint` when required evidence is missing or the requested Assistant promotion is unsupported.
- `blocked` only when required resources or new authority cannot be obtained.

An unrelated scoped desktop change can be handoff-ready while retaining accepted Assistant limits;
that does not promote the Assistant to Stable.

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
merge guard. Verify the resulting merge state. A pre-merge notice is not a completion claim.
