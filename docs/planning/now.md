# XBrainLab Now

最後更新：`2026-09-11`

## Active: reliability baseline

The user approved this complete stage: full desktop workflow acceptance with targeted deep improvements,
two parallel lanes, independent review and one final Windows manual handoff. PR #134 is merged; its
acceptance is historical, not approval of this stage. Obtain current branch/source/worktrees from Git.

### Required outcomes and scope

1. TrainRecord owns result-storage lookup semantics. Analysis, Evaluation render, state and history
   readers no longer infer raw primary/split storage or recreate fallback rules.
2. Architecture checking has one ordered fail-fast reporting loop retaining all66 guards and special
   arguments; its ownership guard no longer reparses three already-read special files.
3. Real Command/UI evidence connects multiple training plans, Stop/restart, persistence, selected-result
   reading and saliency. Reuse effective existing tests instead of duplicating a test platform.

Preserve visible UI, formal Command/query/Assistant contracts, EEG/label semantics, training/saliency
source selection, settings, recipes and artifact formats/readability. No production UI edits are
authorized by this plan. UI/public-contract/schema changes need explicit new approval. No new state
owner, generic catalog/control framework, model/RAG experiment, environment creation, model download,
WSL compaction or unrelated storage cleanup. Assistant retains its accepted bounded limits, not Stable;
only affected shared contracts need regression evidence. Do not relabel historical model runs.

### A: result-read boundary — core worker

Evidence: TrainRecord's primary eval_record and named evaluation_records are two justified views, not
automatically duplicate state. Analysis enumerates saved splits; Evaluation chooses a matching map
record or matching-primary fallback; history requires a saved test record; state projects primary
availability and saliency. These readers currently inspect storage separately.

Implement semantic queries in the existing TrainRecord owner; migrate the four readers and delete
their raw-storage inference. Keep distinct primary, available-split, stored-only, requested-split with
matching-primary fallback, and saliency semantics. TrainingPlanHolder retains evaluation/class-coverage
policy. Application retains publication identity, stale rejection and detached DTO projection. No new
owner; expected five existing production files plus direct tests. Do not remove necessary storage.

Characterize before edits: real three-split records with test/validation primary; base-only artifacts;
base eval plus different same-split sidecar (primary stays base, named split stays sidecar). Preserve
missing/mismatched splits, primary metrics after saliency replacement, cross-fold selection, detached
state/history and stale rejection. Use real record objects and safe artifact IO, not fake persistence.

### B: architecture checker — tools worker

Evidence: check_architecture has607 lines,66 ordered guard calls and duplicated reporting. Preserve the
two initial UI text checks, every individual guard API, headings, violation order, lazy invocation,
fail-fast exit and success text. Mutable-object checking uniquely requires validate_allowlist=True.

Use one private ordered sequence/reporting loop in the existing checker, not a new manifest/plugin.
In the ownership guard retain only three already-parsed special trees for its later checks, preserving
missing/invalid-source handling. No persistent/cross-guard AST cache, guard deletion or gate weakening.
First characterize dispatch order/arguments/output; retain real hostile/allowed source fixtures and
prove a skipped guard is caught. Measure same-workload parse count, elapsed time and peak RSS. Hold at
most three special ASTs; extra peak RSS budget16MiB. If exceeded, redesign rather than waive the budget.
Planning-only WSL diagnostic: three guards715 parses/456files/5.097s; full checker exceeded55s (not PASS).
These measurements are not native/platform acceptance or an overall CI speedup claim.

### C: integration/evidence — main agent

| Flow | Required evidence | Status |
| --- | --- | --- |
| Import/recipe | Success/reload; failure preserves prior data, labels and metadata | Existing evidence mapping; final gates pending |
| Preprocess/epoch | Transforms/rejection, event/class/window semantics, stale prepare rejection | Existing evidence mapping; final gates pending |
| Split/train | Formal Command path, exact subject/fold count, all real checkpoints completed/reloaded | Interactive multi-plan gap investigation pending |
| Stop/restart | Real Stop, terminal identity, old work cannot overwrite new round, restart saves | Focused real workflow evidence pending |
| Evaluation/readback | Three splits, validation primary, base-only/base-sidecar, exact run/aggregate | A characterization pending |
| Saliency/views | Gradient/SmoothGrad, recompute/cancel/select, atomic batch, retained old result, four views | Existing evidence mapping/fault witness pending |
| Runtime/tools | Native launch/settings isolation/close, callback release, honest exits/rerun | B characterization/final native gates pending |

Important success paths may not mock admission, trainer, saving or loading and claim end-to-end proof.
External isolation and deliberate fault injection remain valid. Wrong split, omitted checkpoint, stale
terminal, partial saliency publication and skipped guard must each fail a corresponding existing or
strengthened test. Do not persist faulty source or invent a mutation platform. Retain85% line gate and
branch evidence; no arbitrary new coverage percentage or full-suite run per edit.

### Parallel work, review and recovery

One integration branch/PR accumulates small independently reversible commits for one human test cycle.
This user-approved stage exception preserves per-slice complexity review: deletion candidates, owner
delta and actual production +/-/net LOC. It does not authorize UI/schema/architecture expansion.
Rollback only identified stage commits after checking dependencies; never reset the original checkout.

Workers own A/B source and direct tests; main owns C, shared fixture/config coordination, integration
and this plan. Request ownership before touching another lane's files. Main reviews actual worker
diffs; independent nonauthors judge both safety and target completion, then integrated evidence.
Serialize GUI/GPU/heavy tests in the existing Windows environment. Focused checks and early shared
boundary integration precede final gates; no parallel worker full-suite runs.

Keep this active plan compact: targets, ownership, evidence and unresolved issues. Previous stage
history remains in Git/PR, not active dispatch. Progress is completed criteria/missing evidence, not
commit or inspected-file counts. After context recovery read this plan and actual Git, then continue.

### Delivery and stop condition

Complete A/B/C and resolve in-scope findings before freezing one source. Require all applicable same-head
non-skipped CI, canonical source-diverse data, platforms and UI gates. Reuse equivalent successful CI;
fill missing local/native evidence only. Commands/gates remain owned by docs/validation/README.md and
scripts/dev/handoff_gate_spec.py. Existing native safety/timeouts remain mandatory.

Open Windows GUI plus its single PowerShell live-log console, confirm responsiveness, provide exact
source/restart command and one consolidated manual checklist, then hand control back without monitoring.
Manual findings get affected/adjacent revalidation, not automatic full human retesting. Merge requires
new exact-source manual pass and permission. No environment/worktree deletion in this handoff.

A slice, commit, context compaction or pending CI is not an endpoint. Continue until final handoff or
a genuine new authority/resource blocker. At most three unrelated advisories; never silently downgrade
a required outcome. UI/public-contract changes need explicit approval while independent work continues.

### Current step

Plan persisted before implementation. Next: A/B characterization, C evidence mapping and existing native
test invocation. Original checkout dirty UI/test edits and root settings stay untouched. No current
implementation/test PASS claimed.
