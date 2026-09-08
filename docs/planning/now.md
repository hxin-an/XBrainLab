# XBrainLab Now

最後更新：`2026-09-09`

## Active — Comprehensive architecture, implementation and test cleanup

### Delivery protocol — one Draft, one final manual acceptance

- `#130` is the single long-lived **Draft** integration PR.  Small commits and
  focused CI are construction evidence only: they never request review, manual
  testing, merge, or a completion claim.
- A checkpoint advances directly to the next unclosed inventory row.  Failed CI,
  platform-specific assertions, or direct adjacent regressions are repaired and
  revalidated by the implementation work; they are not handed to the user as an
  interim acceptance task.
- The only manual-test handoff is permitted after every row below is closed,
  every actionable authorized deletion/consolidation is integrated on one clean
  exact SHA, and the applicable final validation is complete.  Only explicit
  user acceptance of that final SHA permits a single merge.
- “Closed” means each area records its owner, real entry/caller evidence,
  relevant test evidence, and one of: removed/consolidated, retained with a
  concrete reason, or an explicit blocking evidence gap.  “Partial” and
  “unreviewed” never qualify for handoff.

| Inventory area | Status | Closure requirement |
| --- | --- | --- |
| Import, interpretation, event/class/channel/montage, preprocess and epoch | Closed | Command, receipt, UI/Assistant entry and real-data/format fixture sweep recorded below. |
| Split configuration, training, stop, retry and result reopen | Closed | Command-boundary, allocation, cancellation, preview and reopen lifecycle evidence recorded below. |
| Evaluation, Saliency and Visualization | Closed | Render/publication owner and consumer/test evidence recorded below. |
| Shared state, publication, async lifecycle, SHA/cache/copy and dependency direction | Closed | Distinct owner/consumer and unsafe-seam evidence recorded below. |
| Assistant parameters, confirmation, execution and UI handoff | Closed | One tool-to-command spine and lifecycle/handoff evidence recorded below. |
| Startup, settings, logs and shutdown | Closed | Runtime/config/log/resource-cleanup ownership evidence recorded below. |
| Scripts, CI, hooks, dependencies, docs and fixtures | Closed | Registration/consumer/fixture sweep and orphan removals recorded below. |

Current phase: source is frozen for final exact-head validation. Do not request
manual acceptance until the applicable final checks succeed on that same SHA.

Completed bounded slice — retired uncalled training convenience wrappers:
`ApplicationService.configure_training()`, `train()`, and `stop_training()` only
construct typed commands and delegate to `execute()`. Repository caller sweeps
covering UI, Assistant, scripts and tests found no caller; those consumers use
the Command API directly. Scope is deletion of these three private-project
convenience methods and only exclusive tests if any exist. Retain the public
`ConfigureTrainingCommand`, `TrainCommand`, `StopTrainingCommand`, command gate,
resource confirmation, cancellation and training runtime. Owners before/after:
ApplicationService remains the command boundary; no owner is added. Expected
production delta was -17 LOC. Direct caller sweep and the focused training
command/stop-runtime suite pass (82 tests); pre-commit Ruff passes. Exact-head
CI remains final integration evidence. A wider Windows workflow run exposed
existing artifact-path and recipe-source failures on direct command routes; it
does not exercise a removed wrapper and remains an inventory follow-up rather
than evidence of this deletion.

Completed bounded slice — retired uncalled split/lifecycle convenience wrappers:
`ApplicationService.configure_dataset_split()`, `clear_datasets()`,
`clear_training_history()`, `reset_preprocess()`, `reset_session()`, and
`new_session()` only construct typed command envelopes and delegate to
`execute()`. A full repository caller sweep found no ApplicationService caller;
the matching names that remain belong to domain/UI owners, not this service.
Scope is deletion of those six methods only. Retain command classes, lifecycle
service, UI actions, Assistant/automation commands, split preview and its
cancellation path. No visible UI or public command contract changes. Owner delta
is zero and production LOC was -33. Direct caller sweep, pre-commit Ruff, and
focused split-preview/lifecycle service protection pass (37 tests). Exact-head
CI remains final integration evidence.

Completed bounded slice — retired uncalled result/query convenience wrappers:
`ApplicationService.evaluate()`, `visualize()`, `saliency()`, `apply_montage()`,
and `query_state()` have no repository caller and only delegate a typed command to
`execute()`. Scope is their deletion only. Retain `EvaluateCommand`,
`VisualizeCommand`, `SaliencyCommand`, `ApplyMontageCommand`, `QueryStateCommand`,
the analysis service, UI ports, headless automation and Assistant tools. No owner,
visible UI, data, result-read or public command contract changes; production LOC
was -20. Direct caller sweep, pre-commit Ruff, and focused analysis/state-query
protection pass (106 tests). Exact-head CI remains final integration evidence.

Completed bounded slice — retired data/interpretation/epoch convenience wrappers:
`ApplicationService` methods for legacy load/labels/table mutation, scan/review/
preview/validate/apply interpretation, and epoch creation merely construct typed
commands and call `execute()`. The caller sweep found one real test use of
`review_interpretation()`; it now uses `execute(ReviewInterpretationCommand)` so
it protects the actual public command/receipt contract. All 13 wrappers are
removed (-141 production LOC in `service.py`; net -155 lines in the commit).
All command types, Data Interpretation two-phase routes, resource receipts,
UI/Assistant entry points and EEG behavior remain. This has no owner, UI, or
public-command change. Ruff passed through the commit hook. The specified
resource-receipt/import-boundary/epoch focused pytest protection now passes on
the Windows environment (6 tests; one expected MNE all-epochs-dropped warning).
Exact-head CI still remains final integration evidence.

Inventory closure — import through epoch: `ApplicationService.execute()` is the sole
mutation command boundary. Dataset/Preprocess panels, Assistant command builders and
headless evidence use typed load, interpretation, metadata, montage, preprocess and
epoch commands; no removed convenience API has a caller. Data Interpretation owns its
two-phase discovery/apply receipt, preprocessing owns detached preparation, and epoch
materialization owns event/window validation. Resource-receipt, content-hash cancellation,
import-boundary, epoch materialization, BIDS duration, format-matrix and checked-in
GDF/MAT real-data tests retain the workflow and fixtures.

Inventory closure — split through result reopen: dataset-generation owns saved split
state/materialization, training runtime owns stop and terminal truth, and ApplicationService
owns command admission plus preview/reopen reads. UI capability ports, Assistant tool
builders and cross-source/product walkthroughs use typed commands. Real-epoch deferred
split tests cover Full session/subject, Individual session, Individual-subject rejection,
preview receipts and materialization; handler-level mock tests retain independent rollback
and exception isolation rather than duplicating that coverage.

Inventory closure — Evaluation/Saliency/Visualization: AnalysisCommandService owns command
execution; ApplicationService owns publication-fenced evaluation/saliency rendering; the
two UI panels consume the capability port. The removed Evaluation/Visualization controllers
had no remaining consumer. Render walkthroughs, source-diverse journeys and publication-
lifecycle tests cover selection, stale/reopen, cancellation and terminal notification.

Inventory closure — shared/Assistant/startup/scripts: immutable view publication, owned-work
registry, training delivery lifecycle and shutdown fence have distinct async owners and
real UI/Assistant/integration consumers. SHA/receipt fingerprints, cache invalidation and
detached copies are TOCTOU/external-resource seams. Assistant tools resolve one runtime and
execute one typed command spine; UI handoff only routes existing workflow surfaces. Runtime
creation, per-user settings migration, secure logs, startup smoke and Assistant resource
shutdown have dedicated owners/tests. CI/handoff/Poe/docs/fixtures retain registered gates;
the unregistered runners and exclusive tests were removed. Architecture compliance guards
pass on the exact pre-freeze source revision.

Import-to-epoch first-pass retention: Data Interpretation lifecycle exports remain
consumed by apply, state, and command-service production paths; preprocessing render
DTO/query boundaries remain consumed by the Preprocess panel and native-stress
evidence.  They are retained, not compatibility-only deletion candidates.  The row
remains partial pending its complete workflow and test/fixture sweep.

Split/training first-pass retention: `ApplicationService` owns split context/preview
and training resource-preview lifecycle; the UI capability port and training panel
consume its model signal, preview, cancellation, shutdown and recommendation reads.
Assistant tool builders, public cross-source smoke and product walkthroughs construct
the typed split/training/stop commands directly. Integration tests cover the command
boundary, split preview and resource confirmation. These are real allocation,
cancellation and result-reopen seams, not the retired convenience API; the row remains
partial pending the remaining fixture/test quality sweep.

Evaluation/Saliency/Visualization first-pass retention: the ApplicationService owns
publication-fenced render operations; the UI capability port and the two panels consume
the render begin/prepare/commit APIs. Product walkthroughs and source-diverse journeys
exercise command execution, while publication-lifecycle integration tests cover stale,
cancelled and reopen behavior. The retired controllers have no replacement owner; the
remaining render APIs are retained. The row remains partial pending test/fixture quality
and result-notification closure.

Assistant/lifecycle first-pass retention: Assistant tools resolve one
`ApplicationToolRuntime` and execute typed commands through ApplicationService; they
fail closed without that runtime. UI `AgentManager` owns presentation, while
`AssistantRuntimeLifecycle` and its dispatcher own asynchronous controller shutdown.
Application shutdown fences, owned-operation cancellation and background waits have
real UI/integration consumers. No second product command spine or unowned shutdown
delegate was found in this pass; the rows remain partial pending settings/log/startup and
test/fixture sweep.

Startup/settings/log/shutdown first-pass retention: Application runtime construction is
centralized in `backend/application/runtime.py`; per-user Assistant settings and legacy
migration are covered by config tests, while repository `settings.json` remains excluded
local state. Secure log storage has dedicated permission/regular-file tests. Startup smoke
is registered in CI and the handoff registry. Product shutdown remains split by ownership:
ApplicationService fences its command/publication work and Assistant runtime owns its
controller/dispatcher/download cleanup. These are distinct resources, not duplicate
control planes. The row remains partial pending full launch/teardown fixture review.

Shared-state/publication first-pass retention: `ApplicationViewPublication` is the verified,
immutable UI/Assistant read model; `OwnedWorkRegistry` is cancellation truth for individual
operations; training publication lifecycle delivers terminal events; and the shutdown fence
is the mutation-admission barrier. UI capability ports, the application renderer, Assistant
tool runtime and integration lifecycle tests each consume these distinct seams. They are not
duplicate mutable state and cannot be collapsed without changing async ownership. The row
remains partial pending cache/SHA/copy and dependency-direction closure.

SHA/cache/copy first-pass retention: resource SHA-256 and scope fingerprints bind reviewed
imports and receipt confirmation against TOCTOU; BIDS resource admission rechecks content on
unreliable timestamp platforms; training recommendations cache only detached matching context;
and detached render/preparation copies keep background work from mutating live product state.
Resource-identity, cache-invalidation, Windows freshness and rollback tests exercise these
boundaries. They are retained as unsafe/external seams, not generic caching duplication. The
shared row remains partial pending dependency-direction and fixture closure.

Scripts/CI/docs/fixtures first-pass retention: CI, Poe, developer docs and the handoff
registry explicitly reference the test runner, source provenance, native smoke, UI capture,
public dataset, data-interpretation, cross-source training, documentation, and dashboard
tools. Retained scripts have a registered artifact or test/document consumer; no candidate
is deleted from filename-only absence. The row remains partial pending the non-registered
development-script and exclusive-fixture sweep.

Completed bounded slice — retired unregistered standalone development runners: repository-wide
consumer sweep found no CI, handoff registry, Poe, documentation, configuration, product,
or other-script consumer for `capture_dialog_button_order.py`,
`consolidate_dataset_storage.py`, `plan_local_model_download.py`,
`run_product_scenario_manifest.py`, `product_scenario_manifest.py`, or
`run_real_data_handoff_gate.py`. Their only consumers are their six exclusive unit test
modules. Delete each script/manifest with its exclusive tests. Retain the registered
artifact-integrity helper, model-download safety policy, handoff gate registry, public-data
and native/UI gates, and every product workflow. This removes 4,765 development/test-only
lines, adds no owner or contract, and makes no UI change. Final reference sweep, whole-tree
Windows Ruff and changed-tree compilation pass. Exact-head CI remains final integration evidence.

### Approved outcome and execution

- Preserve current effective features, UI, EEG semantics and Assistant public contracts. Audit
  vertical user workflows and horizontal ownership together; old tests do not ratify old business
  paths. Delete unused implementation/tests/references, or consolidate necessary behavior into
  existing owners and delete superseded paths. No legacy archive, wrapper or permanent double path.
- Cover import/event/class/channel/montage/preprocess/epoch; split/config/train/stop/retry;
  evaluation/saliency/visualization; Assistant parameters/confirmation/execution/UI handoff;
  startup/settings/logging/shutdown, and scripts/CI/docs. Include shared service/state/events,
  async lifecycles, SHA/cache/copies, dependency direction and test evidence.
- Each reviewed area must produce callable/ownership evidence, justified deletion/consolidation,
  necessary retention or an explicit evidence gap. Static inspection is not performance proof.
- Integrated cleanup: #126--#129 are consolidated on current `main`: unused Study deferred
  subscriptions, unreachable generic command dispatch bindings, unrouted desktop surfaces, and
  hidden saliency selector projections are physically removed.  The four existing owners remain;
  no API, data, Assistant, cancellation, or visible-UI behavior change was introduced.  Direct
  caller sweep and focused candidate tests protect the retained command spine and visible selector.
- UI confirmation status: granted 2026-09-08.  The user explicitly authorizes internal
  `XBrainLab/ui/` deletion/consolidation that preserves visible presentation and behavior.  Integrate
  #127 and #129 after the same caller/behavior review; stop for any visible design, copy, layout,
  interaction, state, or workflow change.
- Repair steps: consolidate #126--#129, compare the merged caller graph to `main`, and run their
  focused protections plus Ruff.  Then continue the approved whole-project inventory by each user
  workflow and horizontal owner boundary, persist each later bounded slice here before editing, and
  accumulate the independently reversible commits on this one candidate branch.  Rebase or resolve
  only direct integration conflicts; stop for a changed public contract, a real caller, or a visible
  UI decision.
- Integrated orphan-tool cleanup: `scripts/dev/cov_report.py` is removed after a sample invocation
  and full repository/CI/documentation sweep found no current caller, registration, test, or evidence
  contract dependency.  Its hard-coded 90% target and exclusions were not current policy; no
  replacement report or test framework was added.
- Current activity: continue read-only inventory across import/data/preprocess/epoch, split/training,
  result rendering, Assistant, startup/config/log/shutdown, scripts, CI and docs.  A new bounded
  implementation record is required before each further deletion or consolidation.  The focused
  integration protection passed 9 tests plus changed-file Ruff; the full selected module has a
  separately reproduced `main` baseline failure when Windows pytest writes BIDS fixtures through a
  WSL UNC worktree, so it is not attributed to this candidate or counted as a pass.
- Integrated obsolete-API cleanup: the uncalled `ApplicationService.preprocess_data()` convenience
  wrapper is removed.  It only delegated `PreprocessCommand` to `execute()`; the complete caller
  sweep found no use, and the direct command-envelope regression plus Ruff passed.  `PreprocessCommand`,
  `execute()`, capability policy, Assistant mapping and UI workflow remain the contract.
- Integrated compatibility cleanup: test-only `ApplicationService.dispose()` and private terminal
  forwarding delegate are removed; lifecycle tests now exercise `close()` and the owned
  `PublicationLifecycle` directly.  The internal visualization saliency re-export shim is removed
  and package exports import canonical saliency names directly.  The caller sweep is clean and the
  focused lifecycle/UI-owner suite passes 8 tests with Ruff.  `close()`, `PublicationLifecycle`,
  package-level visualization exports and all saliency method values remain unchanged.
- Integrated development-profiling retirement (complexity-reviewed):
  `scripts/dev/profile_data_import_e2e.py` (1,509 lines) and its 446-line exclusive unit module
  are removed.  Their only caller relationship was the test importing the script; CI, handoff,
  docs, configuration, product imports, artifact consumers and validation contracts have no
  reference.  This is -1,955 development/test LOC, with no production owner or LOC delta and no
  new module/owner/receipt/compatibility path.  Wizard correctness tests, public fixture/matrix and
  source-diverse data gates remain; no profiler or gate replacement was added.  The reference sweep,
  changed-tree compilation and retained test-runner routing pass.
- Integrated chat-driver retirement: `scripts/dev/chatpanel_confirmation_driver.py` and its
  exclusive unit test are removed.  Their two helper names have no capture workflow, CI, handoff,
  documentation, configuration, product, or other test caller; the reference sweep and changed-tree
  compilation pass.  Product-level Assistant confirmation and cancellation protection remains.
- Integrated legacy-result-controller retirement: unreachable Evaluation/Visualization controllers,
  their Study lazy branches, exclusive tests and stale architecture/import-boundary entries are
  removed.  Product evaluation/visualization continues through ApplicationService and
  AnalysisCommandService; owner count is unchanged.  Focused import-boundary/analysis protection:
  40 passed.  No result-read, saliency, montage, command or UI workflow rewrite was introduced.
- Integrated modal-capture retirement: the unconsumed development-only alert screenshot generator
  is removed after repository/CI/handoff/docs/configuration/test sweep found no caller or artifact
  consumer.  It was not a canonical manual-acceptance or visual regression gate; `ModalAlertDialog`,
  its component tests and all required UI evidence remain.  Reference sweep and compilation pass.
- Completed platform-fixture repairs: reviewed-import preflight expectations now respect the
  `ctime` reliability boundary; BIDS montage snapshots use the normalized request path; and BIDS
  preview freshness expectations preserve the Windows re-fingerprint requirement. These test-only
  fixes retain content identity, receipts, TOCTOU and atomic geometry protections; they do not change
  production safety or caching policy.
- Parallel read-only work covers broader shared/backend/UI structure and Assistant/startup/settings/
  log/cleanup boundaries. Coordinator integrates overlap and stages later bounded source changes.
  UI authorization permits internal behavior-preserving cleanup only, not visual redesign.
- Validation: focused tests/Ruff per slice; exact-head applicable CI and independent deletion review
  before merge. Test/tool-only slices follow approved reviewer/CI merge; product-source slices retain
  required native/hand-test approval. No gate weakening, model downloads or prompt experiments.
- Persist a new bounded slice record before each next implementation. Continue through independent
  authorized slices, not stopping at compaction, first PR or pending CI. If a product decision/manual
  acceptance is required, isolate it and continue independent work; never claim the whole stage done.
- Completion: coverage assessed or explicitly limited, actionable authorized cleanup implemented,
  superseded paths physically removed, current behavior credibly protected, unused artifacts cleaned,
  remaining ownership burdens and decisions reported. Git/PR retain implementation/validation history.
- Current next step: continue the remaining split/training, test/fixture, shared-state and dependency
  sweeps; no manual acceptance is allowed while the inventory table has a partial row.

### Starting candidates and retained findings

Montage/saliency #123 has merged. The first script-cleanup slice removes orphaned/retired tooling
without changing product behavior or gate coverage; Git/PR owns its review, checks and merge status.
The following candidates come from a bounded UI → command → backend → test audit, not proof that
every file, dataset scale or native lifecycle is defect-free. No new must-fix product defect was proven.

### Candidate order and acceptance

1. **Strengthen split/training command-boundary evidence (test-only).** Cover real Full session/subject
   cross-validation, Individual session success and Individual subject rejection through
   ApplicationService. Existing `test_dataset_generation_service.py` strategy tests use fake
   generators/datasets; `test_dataset_generator.py` and atomic-trial tests protect real allocation
   below the command boundary. Assert subject/session membership, leakage exclusion, class rules,
   saved configuration and preview/materialization agreement where a preview receipt is supplied.
   Replace only demonstrably redundant mock cases after stronger coverage passes; do not change
   ratio semantics or require interactive preview for all headless callers.
2. **UI render-wrapper candidate closed as historical.** The named
   `get_saliency_render_publication` and `get_evaluation_render_publication` wrappers are already
   absent. The current typed ports and `ApplicationUiRuntime` delegates have real panel callers;
   they are not deletion candidates. No source change is required.
3. **Command registry candidate closed as historical.** Two-phase interception owns discovery,
   apply, query, and prepared preprocess/epoch routing before the generic handler map. The
   redundant CREATE_EPOCH and interpretation bindings are already absent; remaining generic
   handlers have live focused-service ownership. No source change is required.

Each candidate needs its own approved bounded active plan before product implementation.
Reviewer findings do not expand that slice. Use focused local evidence and exact-head applicable CI;
product behavior changes still need Windows manual acceptance and merge approval.

### Retain with explicit reasons

- Shared architecture review traced view projection/revision acknowledgement, Qt observer delivery,
  backend owned-work cancellation, UI worker cleanup and Assistant runtime projection. These have
  distinct consumers/responsibilities; no duplicate authoritative owner was demonstrated. Large
  ApplicationService/UI runtime files remain maintenance burdens, not justification for a new layer.
- Startup/config/log/shutdown review retains one-time per-user config migration, sanitized secure log
  storage, native resource cleanup and separate backend/Qt/Assistant lifecycle fences. They protect
  live boundaries; mocked model seams do not establish real model quality.
- Public ApplicationService convenience methods need an explicit compatibility decision before
  removal: repository caller scarcity alone cannot settle use of this exported interface.

- Import Apply content checks guard reviewed files before/after loading; the detached preprocess
  Raw copy isolates MNE mutation. Small render request hashes bind owned-operation claims, not EEG
  content. BIDS caches, cancellation ownership and publication guards have real consumers.
- Split preview serialization protects shared generator/trial-selection state. Re-materialization
  and its digest protect the reviewed allocation at later training. Ratios are allocated using
  atomic group counts and rounding; they do not promise exact percentages of displayed epoch rows.
- Headless split-save calls may intentionally omit interactive preview receipts. The desktop
  enforces reviewed preview; do not call headless behavior a bypass without an approved contract
  or a concrete bad allocation.
- Preview Back/Escape requests cancellation and waits asynchronously for worker ownership to end.
  Existing source proves deliberate cleanup, not an event-loop freeze. Measure real cancellation
  delay before changing lifecycle or claiming a defect.
- Large mock-heavy Evaluation/Visualization tests remain presentation/dispatch evidence, not native
  rendering evidence. Map cases to real lifecycle tests before pruning; raw mock counts prove nothing.
- Unreferenced standalone `cov_report.py` and modal capture remain pending stronger retirement
  evidence. Registered legacy-named capture runners and `verify_rag.py` are active, not dead scripts.
- Performance hypotheses requiring measurement: very large result-summary queries and third-party
  MNE cancellation latency. No cache/thread redesign is authorized from static inspection alone.

## Following stages — agreed order

- Finish justified workflow cleanup in small PRs, not a broad rewrite.
- Then build experimental datasets/evaluator covering actual product RAG, first-generation decisions,
  Host intervention and final outcomes separately, held-out English cases and small-model contexts.
- Only afterward conduct prompt/RAG/architecture experiments. The frozen 81-case suite is bounded
  regression evidence, not a complete capability evaluation or a Stable claim.

## Retained evidence limits

- Historical native -11/debug timeout causes remain unproven; diagnostics are not root-cause fixes.
- Fresh contextless Codex takeover remains unverified; guidance audits do not establish identical
  fresh-agent behavior. Git/CI owns identities/approvals; docs/current.md owns product facts.
