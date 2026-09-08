# XBrainLab Now

最後更新：`2026-09-08`

## Active — Remove unreachable desktop surfaces

- Approved comprehensive cleanup slice: physically remove UI code that no product entry point calls;
  preserve all routed UI, Assistant/command contracts and headless service APIs. No visual redesign.
- Evidence: repository callers of `TestOnlySettingWindow` are its exclusive unit test and an explicitly
  unrouted developer contact-sheet tile. The two free render-publication wrappers in
  `ui/application_capabilities.py` have no callers; current panels use owned async operations.
- Scope: delete that dialog and its exclusive test/capture references, remove the two unused UI
  wrappers and any directly orphaned imports/error-copy entries. Do not remove backend TestOnlyOption,
  service render getters, lifecycle guards, or active capture tooling. Existing owners remain unchanged.
- Steps: recheck references; establish affected UI/capture baseline; delete unreachable paths; rerun
  focused tests, lint and same-head applicable CI; independently review caller/deletion mapping.
- Stop condition: routed UI and service consumers remain protected, deleted paths leave no dangling
  imports, checks pass. Product-source handoff remains subject to manual acceptance; no automatic merge.
- UI authorization: approved internal cleanup only; no visible product layout/text/interaction change.
- Rollback: revert this bounded PR, not a compatibility wrapper. No additional owner or state is added.
- Broader plan: test-only split evidence is isolated on its own branch; shared backend/state and
  Assistant/startup audits continue independently. Findings are not authority for unrelated changes.

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
