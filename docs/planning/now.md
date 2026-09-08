# XBrainLab Now

最後更新：`2026-09-08`

## Active — Complete montage mapping and post-training saliency

### Evidence and outcome

- Windows manual test: import BIDS without montage, complete training, then select montage;
  saliency rendering raises an inhomogeneous-array ValueError in `_read_montage_fingerprint`.
- Read-only reproduction: `Epochs.set_channel_positions` preserves unmatched channels as `None`,
  while the saliency context reader assumes a complete numeric N-by-3 array. A mixed 66-entry
  layout reproduces the reported exception without changing EEG samples or channel order.
- User approved the revised plan: Select Channels owns channel removal; manual montage must map
  every retained channel with valid unique electrodes and support at least a topographic map.
  Three-dimensional rendering remains subject to its stronger existing geometry requirements.
- The directly coupled render DTO also assumes every position is iterable. Both assumptions must
  be covered by the real sealed-result publication path, not only a context-reader unit test.
- Start from merged main after the accepted logging/preprocess PRs and their cleanup. Their
  acceptance does not cover this new product repair; Git/PRs retain those historical approvals.

### Scope and steps

1. Mapping worker: share validation between the existing dialog and command admission. Disable
   Apply/Replace Layout for missing, invalid, duplicate or geometrically unsuitable mappings;
   mark problem rows and show one concise English summary. Validate before any mutation or saved
   settings. Apply/restore BIDS must satisfy the current selected-channel contract as well.
2. Results worker: reconcile producer input identity with actual model constructor input selection.
   Omit chs_info only where the existing direct/catalog construction already omits it; retain it
   for consuming models. Preserve weight/data/class/channel/split/run checks and existing policy
   against replacing a layout already used during training. No new compatibility layer or cache.
3. Replace the incomplete-manual-apply happy-path regression with atomic rejection. Exercise real
   epochs/model/sealed results: train and compute without montage, apply complete montage, then
   render topography and eligible 3D without recomputation or data/channel changes. Remove silent
   render-time channel subset selection. Retain missing-coordinate handling only for reachable
   imported-data paths. Cover direct and catalog consuming/non-consuming model contracts.
4. Independent review checks data axis, geometry and real test evidence. Reuse existing owners;
   review complexity thresholds before expanding. Update canonical current/architecture claims
   only where behavior changes. No broad BIDS or SHA cleanup.
5. Open a native UI preview first for design acceptance; then focused evidence and same-head CI
   including source-diverse/visual/platform gates. Deliver one separate PR and exact-source Windows
   app with visible logs. Stop launch monitoring once responsive. New manual pass and explicit merge
   approval remain required; after merge clean task artifacts while preserving durable evidence.
- UI authorization: user approved this plan on 2026-09-08 with “Implement the plan.” Only montage
  confirmation readiness and concise mapping feedback may change; retain layout/theme/button names.
- Manual-test follow-up: PR #123 introduced a dialog initialization regression. With real
  standard_1005 positions, three-run median construction times were main/current 0.179/3.681 s
  for 66 channels and 0.339/13.362 s for 128 channels. Per-row default selection triggers
  full-table validation and repeated stylesheet application before the dialog becomes visible.
  User approved the bounded repair on 2026-09-08: defer edit-signal connections until batch
  population finishes, synchronize once, and avoid unchanged stylesheet writes. No new cache,
  worker, owner, public API or visual change. Add real-Qt/MNE large-mapping regression coverage
  before fixing; preserve invalid/duplicate/geometry rejection and immediate user-edit feedback.
  Compare the same 66/128-channel workloads (target >=80% reduction), then check native direct
  and Assistant opening stages. If other delays remain, measure them before claiming resolution.
- Next: finish native validation of the repaired regression in PR #123, complete exact-head CI, then open Windows
  with visible logs for renewed manual acceptance. Prior CI passed on the previous candidate;
  it cannot certify the upcoming source. Stop only at handoff or a genuine resource/authority block.
- Acceptance: user accepted the native mapping preview on 2026-09-08
  (“我測試過了覺得可以”); this is design approval, not merge approval. Final repaired-source
  Windows manual acceptance remains pending. Prior validation and source identities remain in PR #123.
- Complexity review: explicit BIDS restore also needs pre-mutation validation through its existing
  lifecycle/coordinator, bringing production file count to ten. Reviewed implementation totals
  +288/-112/net +176 production lines before preview-driven refinements.
  No owner is added: command admission, montage lifecycle and model construction retain ownership.
  Delete duplicated command validation/partial acceptance and render-time subset selection; share
  effective constructor context. Keep one coherent montage PR because splitting these admissions
  would leave a bypass. Prefer validation inside existing restore mutation over a new peek/rollback
  API; pause again for scope growth or a new owner, not merely for this bounded file-count trigger.

### BIDS audit boundary

- Separately distinguish missing coordinate sidecars, unreadable/unmatched existing metadata and
  legitimately partial geometry. Local inventory found four of fifteen exports without electrodes
  or coordsystem sidecars; the other eleven use supported CapTrak/metre metadata. File presence is
  not successful parsing, and the inventory does not establish whether original data or conversion
  omitted coordinates. No broad BIDS compliance or dataset-family claim.

## Following work — agreed order

- Audit frontend → backend → tests by user workflow: data preparation, training and results.
  Inspect repeated calculations/validation, SHA, caches, state ownership, compatibility branches,
  async lifecycle and high-mock tests. Use small justified PRs.
- Then establish experimental datasets and an evaluator representing actual product RAG,
  first-generation decisions, Host intervention and final outcomes separately. Keep held-out English
  cases and small-model context budgets explicit.
- Only afterward conduct prompt/RAG/architecture improvement experiments. The existing frozen
  81-case suite is bounded regression evidence, not a complete capability evaluation or Stable claim.

## Retained evidence limits

- Historical native -11/debug timeout causes remain unproven; diagnostics are not root-cause fixes.
- Fresh contextless Codex takeover remains unverified after environment/permission restrictions;
  guidance audits do not establish identical fresh-agent behavior.
- Git/PRs own versions and approvals; docs/current.md owns product claims. Completed implementation
  history belongs in Git, not active dispatch.
