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
| A Map | Every responsibility and direct consumer assigned, retain/migrate/delete rationale and baselines | Complete; independent cross-boundary review passed |
| B Backend | Workflow/composition and monitoring separation; shared lock/admission/publication preserved | B1/B2/B3 committed and reviewed |
| C Controller | Non-Qt proposal/interaction/terminal decisions in explicit owners; real harnesses migrated | C1/C2 committed; C3 implemented and validated |
| D UI host | Concrete presentation separated; no duplicate runtime/publication/turn decisions | D1/D2/D3 committed and reviewed |
| E Integration | Independent boundary review, same-source gates, one Windows GUI/Assistant handoff | Review complete; final CI/native model gates next |

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
All planned implementation and independent boundary reviews are complete. Commit C3 and canonical
architecture truth sync, push one integrated candidate and open its PR. Follow exact-head CI through
all non-skipped success, verifying source-diverse/platform/UI artifacts. Run the missing real bounded
Assistant baseline and normal ChatPanel journey using the shared native Windows environment/caches.
Then open the exact clean candidate with manual_windows.ps1, verify response and deliver one GUI/English
Assistant checklist/restart command. No new manual acceptance or merge permission has been received.
Responsibility maps are in ignored core-audit; final retained groups and evidence limits are below.

### B1: delete method-by-method lazy proxy classes

Baseline core-baseline: 1,656 native cases passed in 85.72s; direct lazy/reset/receipt/walkthrough
adjacent baseline follows before editing. Replace three proxy objects with cached construction of real
services, like existing analysis. Handler bindings defer construction until execution. StateSnapshotService
receives narrow snapshot callbacks; LifecycleCommandService receives narrow reset callbacks, preserving
unmaterialized reads/reset. TrainingConfigurationResetService also clears its recommendation projection.
Remove obsolete proxy-private fixture wiring and retain actual subprocess import/reset protection.
No new production module/class/authoritative owner; existing domain owners and command locks unchanged.
Estimated production +110/-320/net -210 across service/state/lifecycle/reset owners. Revert this commit
as one slice; no migration/schema compatibility path. First slice is not completion of batch B.

B1 adjacent baseline: first attempt had a plan-only source change and is not attested. Second exposed
three absent fixture-path skips (86 passed, gate failed). Existing central data root configured without
download; corrected immutable-source baseline passed 104 cases/16.92s, including all three real receipts
and dock/navigation adjacency. Initial core 1,656 remains passing pre-change behavior evidence.

### D1: concrete Assistant dock view

Independent first UI slice may run alongside B1: introduce ui/chat/assistant_dock.py with concrete
QDockWidget/title widget assembly, fixed-right/no-float topology, panel width, title status/buttons.
AgentManager composes view and retains runtime snapshot replay order, ChatController/input/confirmation
signal routing, visibility/publication and close. View accepts no AgentManager/runtime/state object;
title requests are Qt signals. Delete original widget construction and test-only host button aliases;
tests use concrete view children. Existing main-window QDockWidget contract and visible pixels unchanged.
Estimated production +145–170/-145–170, no authoritative owner added, necessary Qt ownership seam.
Rollback as one view/host/test commit. Core baseline and 104-case adjacent baseline passed before edits.
This is the first UI responsibility group, not completion of AgentManager.

B1/D1 post-change: immutable-source native run first-slices-post-and-next-baseline passed 977 cases
in 74.36s, including lifecycle/reset/import receipts, real dock/walkthrough, training/saliency monitors
and evaluator/product-flow fixtures. Independent B1 review found no blocker; its cold full-state-query
advisory is covered by the expanded subprocess import test. B1 production +143/-363/net -220 across
four files; D1 +186/-150/net +36 across two files. Full typing/integrated handoff remains pending.

### B2: concrete training/saliency operation monitor

Transfer the monitor lock/thread map, start/poll/terminal publication and physical join together into
TrainingOperationMonitor in training_operation_monitor.py. Its only dependencies are TrainingRuntimePort,
OwnedWorkRegistry and the shutdown snapshot callback. Service keeps admission, diagnostics extraction,
result decoration and the existing background-wait order/deadline. Registry remains operation truth;
physical thread lifecycle moves, never duplicates. Preserve exact trainer/saliency generation checks,
0.25s delivery polling, shutdown-fence escape, start failure, self-join rejection and terminal/exit gap.
Delete unused append threading argument. Estimated service -180–200, concrete seam +175–195, net near
neutral; owner count unchanged by the transfer. Roll back service/monitor/tests as one commit.
977-case run is the passing pre-change baseline for owned-work, application and saliency publication
tests. Add missing observable start-failure/self-join witnesses before transfer; independent review
must verify shutdown/publication/physical-exit ordering. No timing or cancellation-policy change.

### D2: consolidate existing presentation projections

Move confirmation current-value classification/formatting and response-to-transcript kind mapping from
AgentManager into existing AgentPresentationService. Manager retains publication IO/error handling and
exact confirmation lease/transport/card lifecycle; no new widget or state owner. Preserve all copy and
fallback values. Delete host projection helpers and migrate high-mock probe fixtures to direct pure
projection tests plus existing actual-manager confirmation/response tests. Estimated production
+90/-100/net -10 in two files; no new module/class. Roll back both owners and tests together.
Run confirmation-current-values, presentation-service, action-card and chat-panel baseline before edits;
existing manager/threading/walkthrough baselines already pass. Transcript admission/staging remains a
separate required disposition after the Controller delivery boundary settles, not blanket retention.

D2 characterization passed 202 cases/11.43s. Early whole-production Basedpyright gate after B1/D1
passed with zero diagnostics (1.39.2); no debt-baseline update. B1 committed 6d7ec130; D1 a19abf1d.

### C1: remove whole-Controller execution dependency

ToolExecutionCoordinator receives only study, registry, metrics and three signal-emission callbacks,
not ToolExecutionHost/self. The immutable reviewed-publication runtime moves from Controller into
the existing execution module. Controller retains context admission and missing-generation rejection;
coordinator binds the supplied generation without changing command-start/completion/error ordering.
Delete the broad host Protocol and migrate real coordinator/evaluator integration seams together.
No new owner or production module; existing execution owner absorbs its runtime adapter. Estimated
production +45/-55/net -10 across two files. Revert those files and direct fixtures as one commit.
Entire unit/llm/agent and lifecycle baseline plus the later strict-recovery/product-flow/evaluator
baseline passed before edits. Verify real generation-bound execution, failure terminal, unknown and
unclassified tools plus unchanged 18-tool surface. Wider delivery/worker disposition still required;
do not replace the Controller with a 19-callback helper.

C1/D2 post plus B2 new characterization: frozen native run completed 802 passed/3 failed (42.70s).
All D2 and B2 cases passed, including both new pre-extraction lifecycle witnesses; C1 is not validated:
two tests patch a removed Controller import and one fixture replaces completion signals after binding.
Repair those fixtures without restoring the broad dependency; repeat the affected Controller evidence.
B2 may now transfer its passing baseline. D2 actual production +98/-93/net +5; projection input typed
as formal ApplicationViewPublication during main review. No handoff claim from this partial run.

### C2: remove obsolete repeated-proposal retry machinery

Reachability review found that strict format retries happen before any proposal is recorded; a valid
proposal executes once, blocks, requests input or pauses at confirmation/UI, then terminalizes. New
user/debug turns reset the session. Only the old loop handler itself requests generation after a valid
proposal, and its threshold requires three proposals in the same turn. Characterize the real typed
worker/controller path (format retry → one handoff → duplicate generation rejected → terminal;
repeat on a new turn) before deletion. Retain one-action admission and strict-envelope retry limits.
Then delete repeated flag/LOOP decision, recent-call JSON/deque state and loop-break counter/handler,
plus exclusively private-loop fixtures; preserve actual one-action/recovery tests and their gates.
No new module/state/owner or public tool change. Estimated production -70–110 across three files.
Independent review must trace all generation continuation paths before declaring unreachable.
Rollback this deletion/test slice separately from C1; do not use a LOC target as justification.

### D3: complete UI admission staging in the existing turn owner

Transfer provisional event queue and accepted activity/prune notice lifetime from AgentManager into
AssistantUiTurnStateMachine, removing the host fields and begin/finish/defer wrappers together. Keep
runtime submit/debug, ChatController transcript mutation, ordered replay to concrete handlers, panel
rendering and exact confirmation/handoff transport in Manager. No new enum, receipt, module or generic
effect interpreter. Complete admission returns an immutable ordered tuple batch (empty means accepted,
None means rejected); superseded completion must not mutate a newer submission. Existing state remains
sole lease/Stop authority; transfer activity/prune lifetime only with exact terminal/reset ordering.
Estimated Manager -70–100, existing turn owner +100–130/net +20–30; authority count unchanged. Add direct
state-owner queue/lifetime witnesses and retain actual Manager synchronous/rejected/stale/Stop/capacity
tests. Run existing turn-state baseline first. Independent nonauthor review of reentrancy and terminal
ordering required. Rollback owner/host/tests as one slice; no visible behavior change authorized here.

B2/C1 post and next baselines: monitor-execution-post-next-baseline passed 761 cases/43.50s on frozen
source. C1's three stale-fixture failures are fixed without compatibility imports/callback lookups;
direct exception pairing/current-state recovery also passed. Independent C1 review found no blocker.
Main independently reviewed B2's complete thread/generation/fence/physical-exit transfer; no blocker.
Same run passed C2's three new real Qt transition cases and existing D3 turn-state/analysis/render tests.
B2 production +234/-217/net +17 (two files including new concrete monitor); C1 +57/-54/net +3;
D2 +101/-93/net +8 after explicit publication typing/formatting. Stage not complete.

### B3: evaluation target revalidation in its analysis owner

Current final summary admission reaches into selected plan/run and re-prepares the catalog. Move target
comparison into AnalysisCommandService, returning the refreshed catalog or None (not just a boolean).
Existing frozen EvaluationModelSummaryPreparation captures the selected plan/run refs alongside its
existing dataset/model inputs at preparation. Remove service's duplicate target selection/comparison;
service keeps locks, training/publication freshness, shutdown/cancel, errors and final result envelope.
No new owner/module/mutable state/schema. Estimated production +40/-40/net near zero across service,
analysis and evaluation_render; revert together. Initial evidence gap corrected: existing service tests
cover summary lock/cancel, not all changed targets. First characterize actual two-phase service rejection
for plan/run/model/dataset/terminal replacement and acceptance with refreshed catalog for unrelated
append. Supplement existing real UI selected-result test; only then transfer and add owner contract tests.
Earlier local target capture must not replace identity with equality or weaken unavailable-target checks.

### C3: retire test-only alternate worker shutdown

Read-only audit found non-QObject worker close and non-QThread fallback reachable only from mocked
constructors, not product factories, scripts, local walkthrough or evaluator. Product always composes
AgentWorker/QThread; absent/deleted worker remains a valid lifecycle state. Remove that alternate path
and exclusive mock tests only after real Qt characterization covers still-unique RAG close exception,
failure/retry, cleanup-pending admission rejection, late RAG/Stop delivery and pending input cleanup.
Existing real lifecycle tests cover worker false/retry, native exit/deferred deletion and idempotency.
Migrate the actual AgentManager debug-flow fixture to real worker/thread; no product init/model change.
Estimated production -25–40 in controller; tests shrink only after behavior replacement. No new module,
owner or fallback. Independently review exact lifecycle equivalence and run Qt lifecycle/integration plus
affected Manager gates. Roll back this slice independently from C2. Do not simplify real timeout/fence
or zero-time native completion protections.

Committed construction slices: B2 62cde20c, C1 897c925a (includes C2 pre-characterization), D2 a3b5db2e.
Independent C2 and D3 review found no remaining blocker after main's D3 ordering/correlation corrections.
C2 production -93 LOC; D3 production +127/-112/net +15 across the existing two owners (formatting may
change counts). Native turn-staging-post-target-shutdown-baseline completed 823 passed/1 failed in
151.66s on immutable source; failure is the new D3 debug witness, not permission to claim D3 complete.
B3's seven exact-target substitutions and refreshed-catalog cases passed against unchanged production;
C3's real worker/thread RAG false/exception/retry and late-delivery fences also passed before deletion.
C3 follows Controller deletion with its own passing pre-change witnesses. Then final disposition/diff
review and canonical same-head integration gates, not another open-ended audit.

C2 committed a55233f0; D3 97b7ba64; next-boundary characterization e8b82ac8. D3 fixture corrected by
clearing its inherited debug.side_effect; 158 focused cases passed/22.07s. B3 final owner transfer is
production +36/-36/net 0 across three existing files after formatting; no added authority. Independent
review found no blocker. evaluation-owner-post-shutdown-ack-baseline passed 428 cases/37.24s, including
the same real target substitutions/concurrent catalog cases, pending/unavailable target removal and
the additional real Qt Stop-ack/RAG cleanup-owner characterization. C3 production is still unchanged.

### Final implementation disposition

C3 removes only test-double shutdown alternatives: production +6/-36/net -30; existing real None/deleted
worker, RAG retry, timeout and zero-time native-exit fences remain. Deleted mock-close cases map to the
passing real Qt witnesses, and the real Manager debug fixture now has exception-safe native cleanup.
Independent C3 review found no blocker. native-shutdown-post-integration passed 542 cases/98.60s;
core-final-typing passed with zero baseline/observed/new diagnostics (Basedpyright 1.39.2). All changed
Python files passed Ruff. These are focused immutable-source runs, not final CI/native-model evidence.

Final cross-boundary review found no further in-scope transfer/deletion requirement. Retained:

- ApplicationService: shared admission/locks, coherent publication/recovery, result envelope and distinct
  two-phase workflow coordination; the four freshness rules are not a generic interchangeable transaction.
- LLMController: Qt composition, prompt/RAG/generation callbacks and terminal delivery; existing attempt,
  execution, interaction and turn owners hold their policy/state without a Controller-shaped collaborator.
- AgentManager: runtime/signal composition, transcript mutation/replay, navigation, concrete interaction
  transport and Qt parent teardown; dock/projections/staging no longer live redundantly in the host.

Current core lengths are 4,189/2,608/1,847 versus 4,640/2,711/2,136 at the base: core -843 lines.
Core plus satellites is production +900/-1,155/net -255; tests are intentionally stronger, not constrained
to shrink. Size is not a clean-architecture or zero-defect claim. Model inference, arbitrary data,
scientific correctness and hung OS/native-process behavior are not proved by focused tests. One final
same-source Windows/Assistant handoff remains mandatory; do not stop at this implementation checkpoint.
