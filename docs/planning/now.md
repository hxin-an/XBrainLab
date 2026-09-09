# XBrainLab Now

最後更新：`2026-09-10`

## Active

## Module-by-module quality baseline

User approved the complete modular cleanup plan and requested implementation on 2026-09-10.
Earlier PR #131 acceptance is historical; it does not approve this stage's source or merge.

### Outcome and scope

Establish a reliable, understandable baseline by deleting historical overdesign, duplicated work and
unnecessary waits. Audit all tracked production, tests, scripts, dependencies, development configuration
and docs. File/LOC/test counts are inventory, not proof of quality or completion.

Preserve visible UI behavior, Command/query/Assistant public contracts, EEG semantics, settings,
recipes and existing result reading. Behavior-preserving UI internals are explicitly authorized.
Unused Python convenience APIs may be removed after checking dynamic registration, configuration,
scripts and documentation. Preserve necessary safety, cancellation, publication and consistency.
No feature/UI redesign, architecture rewrite, model/prompt/RAG experiment, new control plane,
new environment, WSL compaction, backup deletion or unrelated local cleanup.

The user additionally confirmed large-file and code-quality assessment: inspect mixed responsibilities,
coupling, duplicated branches, typing diagnostics and test effectiveness, not only physical LOC. Record
before/after evidence for changes; splitting a file or improving a number alone is not closure.
Previously authorized withdrawal of WSL-compaction tooling and exact residual cleanup remains a
separate infrastructure task; do not restart compaction/shutdown or mix destructive cleanup into
product refactor commits. Revalidate exact targets and active use before that task executes.

### Stage integration exception

One integration branch/PR contains small independently reversible commits, reviewed by module.
The user explicitly approved accumulated stage-level diff and one final Windows manual acceptance;
this stage does not require a PR/manual merge per slice. Slice-level complexity review still applies:
record deletion candidates, owner delta, production +/-/net LOC and split any oversized coherent slice.
This exception does not weaken CI, data/native/Assistant evidence or exact-source merge approval.

Use the existing Windows environment and model/data caches. Preserve the original checkout's dirty
UI/test files and root settings. Worktree/branch/source facts come from Git, not historical paths.

### Module order and ownership

| Module | Includes | Status |
| --- | --- | --- |
| 1 Command/state spine | Admission, capabilities, confirmation, publication, owned work, shared domain ports | Audit and first slice selection |
| 2 Import/interpretation | Loaders, BIDS, labels/classes, channel/montage, metadata, recipes, related UI | Pending |
| 3 Preprocess/epoch/split | Processing, copies, invalidation, preview/materialization, related UI/tools | Pending |
| 4 Models/training | Catalog, resource preflight, settings, stop/rerun, history/checkpoints | Pending |
| 5 Evaluation/saliency/views | Read/publication, SmoothGrad/recompute, four views, stale work/render lifecycle | Pending |
| 6 Assistant/chat | Tool adapters, turns/confirmation/execution, model/RAG lifecycle and shutdown | Pending |
| 7 Shared desktop/runtime | Shell/navigation, shared components, configuration, errors/logging/start/close | Pending |
| 8 Scripts/dev/CI | Launch/setup, Poe/hooks, runners, walkthroughs/evaluators/reports and artifacts | Read-only inventory |
| 9 Cross-module tests/docs | Shared fixtures/guards, dependencies, canonical truth/navigation and coverage gaps | Pending |

Each module includes its callers, tests and related scripts. Domain UI belongs to its domain module;
shared UI belongs to module 7. Script infrastructure has a separate complete review in module 8.
Assign every tracked file to a module (or an explicit retained static/vendor asset group); count and
resolve uncovered files before final review. Generated files are not production inspection evidence.

### Per-module procedure and closure

1. Read owned implementation/tests; trace entry points, authoritative state, mutation/publication,
   async lifecycle and consumers. Record deletion/consolidation candidates and concrete retain reasons.
2. Obtain passing behavior characterization before refactors; reproduce bugs before fixing them.
   Measure only suspected redundant work/waits and their directly relevant paths.
3. Make small deletion/reuse-first changes. Do not replace wrappers with another owner or move code
   solely to reduce file size. Update this plan before each new coherent slice.
4. Improve behavior evidence before removing weak/obsolete tests. Important side effects need a
   lower-mock internal workflow; keep valid external/native isolation. Check selected high-risk tests
   with a bounded intentional behavior break. Preserve known regression cases.
5. An independent non-author reviewer examines actual source/diff/callers/evidence and audit coverage;
   the main agent inspects the resulting diff/evidence. Fix blocking in-scope findings and re-review.

Closure requires complete file responsibility/disposition, resolved confirmed in-scope redundancy,
credible normal/failure/cancel behavior protection and explicit independent review approval. Unknown
in-scope items are not done. Public-contract/visible-behavior decisions require user input; continue
independent authorized work. Later shared-boundary edits reopen only affected module evidence.

### Validation and final endpoint

Focused checks per slice; widen early for shared state/data/publication/lifecycle risk. Preserve the
existing 85% line coverage gate and branch evidence without shrinking the denominator. Select commands
from the existing validation contract/runner; do not create another test-selection or gate framework.

After all modules close, independently review cross-module integration and inventory completeness.
Freeze a final exact commit and require applicable same-head CI, source-diverse data, platform/UI and
affected real-model Assistant evidence. Reuse equivalent successful CI; fill only missing local evidence.
Keep the Assistant's accepted bounded limitations; this stage is not Stable promotion.

Required scenarios include failed import retaining prior data, old recipe/result reading, processing
and split semantics, training stop/rerun, saliency completion/cancel/SmoothGrad/recompute/selector changes,
stale work rejected, Assistant confirmation/failure recovery and runtime shutdown/resource release.
Scripts additionally need honest exit/output outcomes, rerun behavior and safe cleanup boundaries.

Only after all closure conditions pass, deliver one Windows native GUI with its PowerShell live log
(no separate Live Log window), exact source and restart command, consolidated manual checklist, measured
changes and limitations. Confirm responsiveness, then hand control to the user. A slice, commit,
compaction or pending CI is not a stopping condition. Genuine authority/resource blockers are reported.
Manual findings receive affected/adjacent revalidation and an updated delta checklist, not automatic
whole-suite human retesting. Merge only after explicit final-source acceptance and permission.

### Current slice / next step

- Baseline: fetched main `4770b049`; original dirty checkout preserved; source-only integration worktree
  created on `cleanup/module-quality`. Existing Windows Python/pytest are available without installation.
- Slice 1A: remove snapshot-to-training-command coupling. StateSnapshotService uses a training command
  object solely to forward three pure serializers already owned by training_snapshot.py. Both the lazy
  adapter and TrainingCommandService duplicate these wrappers. Route callers directly to the existing
  serializers, remove the dependency and wrapper-only fixture construction; keep lazy heavy imports,
  publication/consistency checks and serializer behavior unchanged. No new owner/module/public type.
- Baseline/after: native Windows state-service tests, training-service tests and directly selected real
  application configuration/reset/query tests, plus changed-file lint. Rollback is one slice commit.
- Next: obtain passing baseline, implement and independently review slice 1A; finish tracked-file
  inventory and inspect remaining lazy dispatch paths. Script inventory runs read-only alongside this.
- Blockers: none established. No module is complete and no manual candidate is being offered.

### Reviewed slices and concurrent work

- 1A snapshot/training-command decoupling: before/after 139 native Windows focused cases passed;
  changed-file Ruff and format checks passed. Independent `snapshot_review` approved actual diff and
  caller/lazy-import evidence, no blocking findings. Production +16/-50/net -34, no new owner. This is
  slice evidence, not module closure or measured speedup. Retain model-name fallback/detachment
  characterization as a next test-quality check within the snapshot audit.
- Script inventory: 106 tracked files on main, 66,204 physical lines. Earlier stale-branch candidate
  names were discarded after exact checkout verification. Registry/CI/evidence scripts are not dead
  solely because they lack product callers. Full domain semantics and actual deletion still pending.
- 8A authorized concurrent slice: inspect and reproduce missing UI-evidence script routing in
  ci_change_scope.py; ensure changed visual evidence producers trigger existing visual lanes. Add
  precise path-classification regression before the smallest policy fix; preserve non-visual routing,
  gate requirements and CI cost boundaries. Worker owns that script and its existing test file only.
  Baseline/after: focused CI scope tests and changed-file lint; rollback one commit. No public/UI change.

### Recovery after context compaction

Read this whole active plan, Git status/diff/worktrees and current worker/session state first. Continue
the next unfinished authorized step immediately; a recovery summary is not an endpoint. Preserve the
module table, current slice, exact evidence and outstanding reviewer findings here before context loss.
Do not dispatch from older completed PRs, recreate environments, discard active work or stop because a
single slice has passed. Keep this file the sole active plan until the stage is actually complete.
