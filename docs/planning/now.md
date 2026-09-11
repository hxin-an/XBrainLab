# XBrainLab Now

最後更新：`2026-09-11`

## Active: complete internal refactor, one integrated acceptance

PR #135 is merged and manually accepted; its narrow result-read/checker/evidence work is finished.
It does not establish whole-project architectural cleanliness. The user approved this complete stage
and requested implementation with one final Windows manual acceptance. Git owns source identity,
branches, dirty state and worktree inventory.

### Outcome, authority and limits

Establish a reliable, understandable baseline across production, UI internals, Assistant wiring,
tests, scripts, development settings and documentation entry points. Eliminate proven unused
capabilities, duplicate policy/state/adapters and unnecessary measured work; preserve needed safety.
Every tracked file must be assigned to a module and disposition. Listed/scanned is not deeply read.
Every module needs actual entry points/callers, owners, evidence and a retain/change/delete decision.

The user approved one integration PR accumulating independently reversible commits, including the
stage-wide PR-size exception; per-slice complexity review remains mandatory. UI internal refactoring
is authorized only with visible behavior unchanged. Preserve Command/query/Assistant public contracts,
EEG semantics, supported settings/recipes/artifact readback, confirmation, cancellation and publication.
No unknown external convenience API preservation is required, but check dynamic registration,
configuration, scripts and docs before deleting. No legacy relocation or empty compatibility shell.

No UI redesign/public contract/schema change, architecture rewrite, model/prompt/RAG experiment,
environment creation/download, WSL compaction or unrelated storage cleanup. Existing original dirty
UI/test edits, root settings, data, Windows manual app and shared environment remain protected.
New public decisions need permission; continue unaffected authorized work if one area is blocked.

### Ordered batches and completion gates

| Batch | Work | Required completion | Status |
| --- | --- | --- | --- |
| 0 Inventory | All tracked source/tests/scripts/CI/hooks/dependencies/docs entries | No unassigned file; module responsibilities/callers/tests/dispositions identified, open investigations explicit | Enumerating |
| 1 Command/runtime | Admission, detached prepare/commit, queries, cancellation, terminal/publication | Unique decision owner; duplicate orchestration removed without weakening stale/nonblocking/failure behavior | Pending |
| 2 Data | Import/review/recipe, classes/channels/montage, preprocess/epoch/split | Real semantics/rollback protection; copies/caches/fingerprints justified or removed | Pending |
| 3 Training/results | Subject/folds, Stop/restart, persistence/reload, Evaluation/Saliency/SmoothGrad/views | Clear lifecycle/storage/publication; no old-work overwrite or partial result publication | Pending |
| 4 Consumers/tools | UI internal refresh/dialogs, Assistant wiring, startup/settings/log/close, scripts/Poe/CI/hooks/deps/docs | No consumer-owned duplicate policy; retained tools have real entry points; obsolete paths/tests removed | Pending |
| 5 Integration | Coverage completeness, cross-boundary independent review, frozen candidate | All batches closed, applicable same-head CI/data/platform/UI/Assistant gates pass; one Windows handoff | Pending |

Tests and related scripts are cleaned alongside each batch, not deferred wholesale to batch 4.
Source inventory and bounded measurement output use ignored build/dev-artifacts, not a new platform.
Keep the module ledger and next step here; retained evidence is indexed here, not duplicated in logs.

### Slice method and review

Trace actual caller/owner -> passing characterization (or real defect red test) -> delete/reuse/refactor
-> identical focused/adjacent verification -> review actual diff -> integrate a small commit.
Before a complexity-triggering change record deletion candidates, owners before/after, production
+/-/net LOC, necessity and reversible split. Large-file size is a risk signal, not a deletion target.
Reuse existing owners; no generic transaction/control/test framework or added authoritative owner.

Use at most two non-overlapping workers; main owns integration, shared boundaries and this plan.
Independent nonauthor review is required for high-risk data/lifecycle/publication and final closure.
Reviewers inspect actual source/diff/evidence: reachable safety/contract/regression gaps block;
speculative hardening and new product abilities do not expand the stage. No duplicate broad reviewers.
Do not call a module finished with unexplained retain items or unresolved in-scope evidence gaps.

### Test and resource strategy

Prefer real domain objects, minimal EEG data and actual save/reload through Command workflows.
Keep mocks for external/native isolation and intentional faults; replace mock-only product-success
claims before deleting tests. Map removed cases to retained stronger behavior protection; don't shrink
the coverage denominator to claim improvement. Reuse existing fixtures/runners, not a second framework.

Required behavior matrix: normal completion; rejected operation preserves prior state; cancellation;
Stop/restart; selection changes; save/reopen; stale callback rejection; atomic saliency publication;
native cleanup. Fault witnesses include wrong split, omitted checkpoint, stale terminal and partial
saliency where applicable. Assistant retains approved capability/confirmation/visible-result behavior;
affected inference paths require applicable real-model evidence, not an assumed Stable promotion.

Retain the 85% line gate and branch evidence; review high-risk missing branches rather than setting
an arbitrary percentage. Measure suspected redundant queries/SHA/copies/waits and existing test/CI
timings before optimizing. No speculative caches or speedup claims.

L0/L1 focused feedback per slice; early adjacent integration for shared boundaries. Final same-head
CI owns full regression, source-diverse/platform/applicable UI evidence. Reuse equivalent successful
CI artifacts; fill only missing necessary native/Assistant evidence locally. Commands/contracts remain
in docs/validation/README.md and scripts/dev/handoff_gate_spec.py, not a copied gate list.
Serialize heavy native/GPU work in the existing environment. Enforce bounded native process safety.

### Persistence, endpoint and delivery

Update batch status, next step, exact evidence pointers, ownership and blockers while working. On
compaction/restart inspect this plan, Git/PR and owned sessions, then continue the unfinished step.
Commits, worker reports, CI pending and compaction are checkpoints, not endpoints or requests for the
user to say continue. Don't ask for per-batch manual tests or merges. Report progress by completed
criteria and open evidence, with production/tests/scripts +/-/net counts, never invented percentages.

After all batches and independent completeness/cross-boundary review, freeze one candidate. Require
all applicable exact-source checks; never relabel old PR evidence as this candidate's pass. Deliver
outcomes, retain reasons/limits and one flow-organized checklist. Open native Windows GUI with one
PowerShell live-log console, verify responsiveness, provide the exact restart command, then hand over
without continued monitoring. Manual defects get affected/adjacent checks and a new accepted source,
not automatic whole-suite human retesting. Merge only after new explicit acceptance and permission.
After authorized merge preserve required evidence and safely remove only this stage's disposable work.

Completion means the agreed internal refactor and direct protections are complete, not universal
absence of defects, scientific validity or all-dataset/model support.

### Current step / module ledger

Fresh worktree created from merged main; original checkout is unchanged. Establish tracked-file
inventory and bounded module investigations before production edits. Native test environment remains
the existing Windows venv; confirm invocation and owned-process safety before running characterization.
Main: command/runtime boundary and inventory integration. Worker assignments follow after this plan
is committed; workers must not edit shared plan or run simultaneous heavy suites.
