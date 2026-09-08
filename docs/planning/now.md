# XBrainLab Now

最後更新：`2026-09-08`

## Active — Finish accepted logging/preprocess merges

- User confirmed Windows manual tests passed for both PR #121 and #122 and explicitly authorized
  both merges on 2026-09-08. The partial-montage saliency defect is a separate follow-up, not a
  claim of either PR. Git/PR comments own exact source identities, checks and acceptance evidence.
- PR #121 is merged. Integrate its already-approved changes into #122, resolving only this shared
  planning document; verify no product edits beyond the two accepted diffs, then require all
  applicable exact-head CI checks before merging #122. No duplicate local full suite.
- After verified merge, remove clean merged worktrees and disposable handoff copies/probes after
  retaining necessary failure/acceptance evidence and checking active processes. Preserve original
  data, durable results, shared environments/caches, root dirty work and settings.json.
- Endpoint: both approved merges and safe cleanup, then proceed to the bounded defect below.

## Next — Partial montage after training blocks saliency rendering

### Evidence and outcome

- Windows manual test: import BIDS without montage, complete training, then select montage;
  saliency rendering raises an inhomogeneous-array ValueError in `_read_montage_fingerprint`.
- Read-only reproduction: `Epochs.set_channel_positions` preserves unmatched channels as `None`,
  while the saliency context reader assumes a complete numeric N-by-3 array. A mixed 66-entry
  layout reproduces the reported exception without changing EEG samples or channel order.
- Restore this supported partial-layout boundary without inventing coordinates, dropping channels,
  discarding valid results or weakening model/data/channel identity validation.

### Scope and steps

1. From merged main, add a focused failing test covering completed saliency → partial layout apply
   → actual render preparation. Include absent, partial and complete coordinates and unchanged
   sample/channel identity; distinguish spatial-view eligibility from non-spatial results.
2. Trace the existing montage/context owners and remove or reconcile the conflicting assumption.
   Prefer reuse/deletion; no new cache, receipt, owner, generic validator or broad SHA cleanup.
3. Validate focused real-data/context/render boundaries and have an independent risk reviewer
   check result preservation and spatial semantics. Use exact-head CI for formal handoff gates.
4. Deliver a separate small PR and exact-source Windows manual-test build. Product merge requires
   fresh explicit user acceptance; previous PR approvals do not authorize this repair's merge.
- UI status: no visible layout/copy/interaction change is approved for this new slice. Keep fixes
  in the backend if possible; request confirmation before any UI-file or visible behavior change.
- Stop/escalate if the repair requires a new public policy for replacing already-used spatial
  coordinates or changing channel/model input identity. Do not silently broaden the contract.

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
