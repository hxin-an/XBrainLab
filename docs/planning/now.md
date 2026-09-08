# XBrainLab Now

最後更新：`2026-09-08`

## Active — Comprehensive cleanup, bounded product handoff

### Outcome and claim boundary

- Preserve current effective features, UI, EEG semantics and Assistant public contracts. Remove unused
  implementation with its exclusive tests/references; consolidate redundant state into existing owners.
  Do not create legacy archives, replacement wrappers, new control planes or arbitrary deletion quotas.
- Workflow review covered import/event/class/channel/montage/preprocess/epoch; split/train/stop/retry;
  evaluation/saliency/visualization; Assistant execution and UI handoff; startup/config/log/shutdown,
  shared publication/async ownership and developer tooling. This is a traced risk assessment, not a
  claim that every file, dataset size or native timing path is proven defect-free.
- The real split test slice now protects both public shorthand and reviewed CV configuration paths.
  Shorthand trial/session/subject remains live in Assistant/scripts; CV split_config tests alone must
  not replace its adapter protection. Mock generator cases were replaced by real service assertions.

### Current bounded source slices

1. Remove unused Study deferred-controller subscriptions: no repository caller; retain lazy controller
   caching, direct subscriptions, locking and application/TrainingStateService observer order.
2. Delete unrouted TestOnlySettingWindow, exclusive tests/capture tile/error copy, and two uncalled UI
   render wrappers. Keep backend TestOnlyOption, headless service getters and owned render operations.
3. Remove unreachable generic command bindings/lazy proxies already owned by detached discovery/apply,
   epoch and query routes. Keep SET_MONTAGE's live serialized route and focused-service APIs. Preserve
   positive workflow tests; envelope checks alone do not establish successful execution.
4. Remove hidden Saliency scope/class widget projections. The visible selector supplies renderer
   mode/key and display identity; preserve All, exact-key single class, 3D first-available fallback,
   repeat selection and native binding invalidation. No layout/text/interaction redesign.

Each slice has a separate branch/PR and independent review. No authoritative owner is added.
The source edits are complete with focused characterization; Git/PR owns exact commits and CI evidence.
Next: finish same-head applicable CI, then hand-test/approve product candidates in order. Do not merge
product source without required acceptance. Test/tool-only approved slices may notify and merge after
review and successful checks. Remove merged worktrees/artifacts only after checking ownership and use.

### Validation and stop condition

- Focused tests and lint are the local feedback loop; reuse exact-head CI for regression, platform,
  source-diverse data and applicable visual evidence. No duplicate full local run or gate weakening.
- Hidden-state deletion replaces private-widget assertions with visible selection -> renderer arguments.
  Removed private handler-map assertions do not justify accepting UNSUPPORTED_COMMAND for live routes.
- UI authorization covers internal behavior-preserving cleanup, not visible redesign. Windows human
  acceptance remains distinct from automated native/default/DPI evidence.
- This wave reaches its endpoint when product candidates are ready for the required hand test, or a
  necessary resource/decision is genuinely missing. Do not stop merely at compaction, push or pending CI.
  Report remaining architecture debt honestly; do not label the entire project clean.

### Retain and next decisions

- Retain content checks guarding reviewed import files before/after loading, the detached MNE mutation
  copy, split preview serialization/re-materialization identity, and small owned-render request hashes.
  Their current trust/mutation boundaries are not equivalent to gratuitous EEG content hashing.
- View projection/revision acknowledgement, Qt event delivery, backend cancellation identity, UI worker
  cleanup and Assistant lifecycle projection have distinct responsibilities and real consumers.
  Per-user config migration, secure sanitized logs and backend/Qt/Assistant shutdown fences remain live.
- Three follow-ups after handoff: (a) decide the public compatibility policy before removing exported
  ApplicationService convenience methods; (b) remove ignored UI refresh compatibility arguments in a
  separate mechanical slice; (c) inspect full-environment restore cost in CI aggregation from observed
  timing before changing its dependency/provenance contract.
- High-mock presentation tests are not native/scientific proof, but mock counts alone do not authorize
  deleting them. Preserve cases with distinct reachable behavior and stronger real-lifecycle complements.
  Large service/runtime files remain maintenance burdens; size alone does not justify new layers.
- Native third-party cancellation and very large result-history latency remain measurement gaps, not
  proven defects. Standalone coverage/modal utilities lack enough retirement evidence; active capture,
  handoff and RAG tools stay in place.

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
