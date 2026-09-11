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
| Split/train | Formal Command path, exact subject/fold count, all real checkpoints completed/reloaded | New real 3-subject/5-fold Command workflow passes |
| Stop/restart | Real Stop, terminal identity, old work cannot overwrite new round, restart saves | Stop after first saved plan; append 15 plans; 16 saved results pass |
| Evaluation/readback | Three splits, validation primary, base-only/base-sidecar, exact run/aggregate | A characterization and selected-run persisted-array equality pass |
| Saliency/views | Gradient/SmoothGrad, recompute/cancel/select, atomic batch, retained old result, four views | Real Qt/lifecycle suite passes; partial-batch and stale-terminal faults detected |
| Runtime/tools | Native launch/settings isolation/close, callback release, honest exits/rerun | Native close/callback tests pass; final candidate launch remains required |

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

Plan committed before implementation. Original checkout dirty UI/test edits and root settings remain
untouched. Native baseline: existing Command/FIF and deterministic persistence3passed9.14s; A real
artifact characterization2passed4.66s before source edits. Core reader migration independently reviewed;
214 direct tests pass. Existing primary API reused, no new owner, five production files net+6LOC.
Native Command/Qt/saliency adjacent evidence160passed77.44s includes the new multi-plan workflow and
exact selected persisted-array equality. Earlier fixture failures and hook-found late binding were fixed,
not waived. Final CI still required; local counts are scoped evidence, not product certification.

B legacy dispatcher removed. Reviewer rejected self-referential dispatch expectations; independent
literal original66-guard contract now replaces them and caught a real changed heading, now restored.
285 native tests cover the full checker unit suite, final analysis fixtures and exact multi-plan flow.
WSL same-workload
ownership measurements:458->455parses;3.656305->3.666912s; peak43480->41168KiB. This supports removal
of three redundant parses and bounded memory, not overall speedup or native/platform acceptance.

Process-only fault witnesses detect omitted model checkpoints, wrong-split labels, incomplete saliency
publication and out-of-order old terminals. The first wrong-split probe failed on a fixture interface,
so it was corrected and rerun to fail on the actual wrong labels; that initial probe is not evidence.
Independent original-guard contract also detects omitted/reordered guards. Faulty source is not saved.

Final callable-list simplification is independently reviewed; its three contract tests pass. Freeze
the candidate, verify exact-head CI/source-diverse/platform gates and launch Windows. Runtime source
and tests must not change during
commit hooks; hooks temporarily stash unstaged work. CI/PR owns live gate status, not this plan or
older local counts. The remaining endpoint is one Windows handoff and new manual acceptance;
the original dirty checkout, user settings and shared environment remain protected.

CI follow-through: first candidate `a63301d5` fails eight backend and one UI unit tests: legacy
test doubles in `test_application_service.py`, `test_saliency_render.py` and
`test_training_result_presentation.py` lack the semantic result queries, or MagicMock invents
a saved test result. Real integration shards, source-diverse data, static checks and walkthrough
passed. Repair only these directly affected fixtures, prefer concrete result records, retain all
observable assertions, then run focused native tests and new exact-head CI. No production fallback
or UI change is authorized by this finding; final Windows handoff remains the endpoint.
The three fixture files are repaired:336 backend and7 UI native tests pass. Production source is
unchanged from the first candidate; a new exact-head CI run is still required, not a waiver.
