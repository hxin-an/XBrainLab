# XBrainLab Now

最後更新：`2026-09-08`

## Active — Comprehensive architecture, implementation and test cleanup

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
- Active implementation sub-slice — development profiling retirement (complexity review): delete
  `scripts/dev/profile_data_import_e2e.py` (1,509 lines) and its 446-line exclusive unit module.
  The caller audit finds only the test importing the script; no CI, handoff registry, docs,
  configuration, product import, artifact consumer, or validation contract invokes its ignored
  timing artifact.  This is development/test code only, production owners before/after: none,
  production LOC delta: 0, no new module/owner/receipt/compatibility path.  The direct deletion
  delta is -1,955 development/test LOC; splitting is unnecessary because the script and test are
  one inseparable orphan pair and rollback is one commit.  Retain wizard correctness tests, public
  fixture/matrix and source-diverse data gates; do not replace them with another profiler or weaken
  any gate.  Validate full reference/registration sweep, changed-tree compile, and the retained
  `run_tests.py` routing.  Stop for an artifact consumer or evidence-contract reference.
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
- Next: independent review and CI for the real split test slice; isolated source slices remove unrouted
  desktop surfaces, unused Study deferred subscriptions, and unreachable generic command bindings.
  The split tests retain real shorthand trial/session/subject coverage because Assistant/scripts still
  use that adapter; CV split_config coverage alone is not an equivalent replacement.

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
2. **Remove unused UI render wrappers (separate product-source slice).**
   `XBrainLab/ui/application_capabilities.py` still defines
   `get_saliency_render_publication` and `get_evaluation_render_publication` without runtime callers.
   Panels use the owned begin/run/commit helpers instead. Delete only these unused wrappers after
   final caller recheck; retain service getters used by headless MOABB scripts and integration.
   No visible change, no owner delta. Validate affected UI capability/panel paths and source guards.
3. **Inspect redundant command registry bindings before deletion.** Two-phase interception in
   `ApplicationService._execute_command_boundary` precedes the generic handler registry.
   CREATE_EPOCH and interpretation entries may be redundant; PREPROCESS still includes a live
   SET_MONTAGE confirmation route. Prove reachability per binding before removing anything.
   Direct focused-service methods have standalone/test consumers and are not automatically dead.

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
