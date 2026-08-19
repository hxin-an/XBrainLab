# Changelog

Important user-visible changes are recorded here. Detailed development history remains available in
Git and merged pull requests.

## [Unreleased]

No user-visible changes are queued after the Local Assistant baseline.

## [0.7.0] - 2026-08-20

### Added

- A local Granite-powered Assistant panel with a strict 18-action workflow surface, backend-owned
  capability checks, confirmations, and correlated GUI handoffs.
- Model-free walkthrough profiles for response presentation, contract failures, complete workflow,
  and lifecycle/navigation diagnostics.
- Explicit Assistant actions for importing EEG data, opening decision dialogs, running bounded
  preprocessing commands, controlling training, navigating result panels, and computing Saliency
  through the existing product workflow.

### Changed

- Assistant mutations now enter the same `ApplicationService / Command API` used by the desktop UI;
  the model does not own a second workflow state or capability policy.
- The Assistant panel uses stable onboarding, compact semantic result cards, clearer confirmation
  cards, and content-aware user-message geometry.
- Direct preprocessing parameters must be present in the latest user request before execution;
  missing or unverifiable values receive a normal clarification response without a tool side effect.

### Fixed

- Local model installation, deletion, cache validation, progress, cancellation, and retry lifecycle
  issues found during manual testing.
- Assistant panel navigation, GUI handoff cancellation, training confirmation, Compute Saliency,
  transcript layout, and first-message rendering regressions found during the v0.7 manual walkthrough.

### Release boundary

- This is a source/local Assistant baseline, not a signed installer or a safety-zero-tolerance claim.
- The fixed 2B model remains bounded by its measured semantic-selection limitations; deterministic
  schema, capability, provenance, confirmation, and one-command guards do not certify intent accuracy.
- MCP is not a v0.7 product capability. Scientific model quality, arbitrary dataset support, and
  product 1.0 remain outside this release claim.

## [0.6.0] - 2026-08-15

### Added

- A reviewed desktop workflow from EEG import through preprocessing, epoching, dataset split,
  training, evaluation, and saliency visualization.
- Formal BIDS subject selection, reviewed label/event interpretation, recipe reuse, and centralized
  local dataset storage contracts.
- Backend-owned operation identity, progress, cancellation, stale-result rejection, and atomic
  publication for long-running product work.

### Changed

- Standard dialog actions now place Cancel on the left and the primary action on the right.
- Filtering and epoch controls use consistent visible states and bounded responsive layouts.
- Each Start Training action owns an independent fold round; Evaluation and cross-fold Saliency no
  longer combine overlapping folds from different rounds.
- Generated development evidence moved out of tracked `artifacts/` into ignored exact-purpose build
  roots; stale dashboards, screenshots, and historical logs were removed from current navigation.

### Fixed

- Explicit cumulative Saliency recompute now admits a fresh lifecycle and preserves verified methods.
- Evaluation retains one cross-fold Summary per completed training round.
- BIDS import, label parsing, progress ownership, state preservation, and preprocessing rollback
  regressions found during manual desktop testing.

### Release boundary

- This is a Windows Desktop GUI/source baseline, not a signed installer.
- Assistant readiness, scientific model quality, arbitrary dataset support, and product 1.0 are not
  claimed.

## [0.5.6] - 2026-02-08

Legacy development baseline before the desktop product-foundation consolidation. It was a package
version, not a public GitHub Release. Earlier details remain in Git history.
