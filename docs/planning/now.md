# XBrainLab Now

最後更新：`2026-09-12`

## Active: three-core responsibility refactor

The user selected internal responsibility repartitioning and approved implementation of the complete
plan after accepting PR #136. Cover ApplicationService, LLMController, AgentManager and directly coupled
production/test/script consumers. Preserve visible UI, Command/query, 18-tool, model/prompt/RAG policy,
data, settings and result formats. Internal UI edits are explicitly approved. Repartition/merge internal
modules, but no parallel control plane, generic transaction framework, compatibility shells or helpers
manipulating private core state. Necessary Qt parent ownership is not such a dependency. No new
environment/download, storage migration or WSL compaction.

## Required outcomes

- ApplicationService retains formal entry, shared admission/lock boundaries, result envelope and coherent
  publication coordination. Workflow preparation/validation/assembly belongs to focused services; lazy
  composition must preserve cheap startup. Concrete training/saliency monitoring needs a cohesive boundary.
- LLMController retains Qt worker wiring, generation scheduling and runtime/turn coordination. Correlation
  and cancellation belong to turn owner, admission to attempt owner, execution to execution owner, and
  pending confirmation/handoff to interaction owner.
- AgentManager retains composition, signals, input forwarding and UI lifecycle. Separate concrete dock,
  confirmation and transcript presentation without another runtime/publication/turn authority.

Trace each responsibility group's real entry points, state readers/writers, failure/cancel/publication,
destination, tests and retained rationale. Unknown/deferred in-scope groups are not complete. Reuse the
previous audit, not another whole-project inventory. Detailed maps may use ignored
build/dev-artifacts/core-audit; this remains the only active plan.

Each slice: passing characterization (RED/GREEN for actual bugs), responsibility transfer and deletion
of old implementation/state, identical plus direct adjacent tests, actual-diff review, rollbackable commit.
Report core AND satellite production +/-/net, dependencies and authoritative owner delta. No per-file
LOC quota or coverage-denominator manipulation. Update the bounded slice record before proceeding.

## Ordered batches

| Batch | Required result | Status |
| --- | --- | --- |
| A Map | Every responsibility and direct consumer assigned, retain/migrate/delete rationale and baselines | In progress |
| B Backend | Workflow/composition and monitoring separation; shared lock/admission/publication preserved | Not started |
| C Controller | Non-Qt proposal/interaction/terminal decisions in explicit owners; real harnesses migrated | Not started |
| D UI host | Concrete presentation separated; no duplicate runtime/publication/turn decisions | Not started |
| E Integration | Independent boundary review, same-source gates, one Windows GUI/Assistant handoff | Not started |

At most two non-overlapping workers; main owns common boundaries, source identity, plan and integration.
High-risk data/locking/cancellation/publication/Qt shutdown changes require independent nonauthor review.
Final review inspects all dispositions, actual paths/diffs/tests, not green CI or LOC alone. No unrelated
robustness expansion. No commit while workers/tests change source: hooks stash unstaged files.

## Validation and complexity

Protect normal execution, rejected mutation, stale prepare/rollback and nonblocking published queries;
multi-subject/fold training, Stop/restart and stale terminal; result reopen and selected saliency
recompute/cancel/atomic publication/display; Assistant direct preprocess, ordinary response,
confirmation/handoff identity, Stop/New Chat, RAG unavailable, worker failure, deactivate/re-enable/close.
Use actual Command/domain/Qt delivery/persistence; mocks isolate external work or inject faults.
Removed tests map to retained behavior; script/evaluator fixtures must not simulate obsolete private APIs.

Use the shared Windows environment and existing bounded native runners; serialize heavy/GPU work,
explicit timeouts and owned-process cleanup. Keep the user's accepted app unchanged. Focused L0/L1 per
slice; final same-head CI supplies full regression/typing/source-diverse/platform/UI gates. Fill missing
native/model journeys using canonical validation/registry, not duplicate full local runs. Preserve the
85% line gate and branch evidence; inspect directly risky missing branches.

One integration PR and this stage's >1,500 production LOC PR-size exception are user-approved. Slice-level
complexity review remains: before a trigger record deletion candidates, owners before/after, estimated
production +/-/net, necessity and rollback/split. No new public contract or parallel authority; a necessary
authority migration removes the original owner in the same slice.

## Endpoint and persistence

Continue all batches/reviews/gates, not stop at a slice, commit, pending CI or compaction. Recover this
plan, Git and owned sessions and continue the next step. Only user pause or genuinely missing authority/
resource blocks earlier work. No per-batch hand tests/merge. Freeze one integrated candidate; open exact
native Windows source with one PowerShell log, verify response, provide restart command and one
GUI/English Assistant checklist, then stop monitoring. Merge only after new exact-source acceptance and
permission; bounded cleanup follows. No zero-defect or Stable Assistant claim.

## Current next step

Source: build/dev-artifacts/core-responsibility, from merged main 6fbc5d5c. Original dirty checkout,
accepted complete-baseline app/evidence, user settings/data and shared caches remain protected.
Map backend locally and delegate read-only Controller/UI maps, then run characterization before the
first production slice. No production edits or candidate PR yet.
