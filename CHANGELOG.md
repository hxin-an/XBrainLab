# Changelog

Important user-visible changes are recorded here. Detailed development history remains available in
Git and merged pull requests.

## [Unreleased]

No user-visible changes are queued after the Desktop Workflow Stabilization baseline.

## [0.9.0] - 2026-08-31

### Added

- Reviewed EEG/BIDS import now includes Dataset-owned Electrode Layout handling, clearer event/label
  interpretation, and recipe Save／Reload for repeating an import configuration while its source files
  remain in place.
- Training supports fold-local class loss weighting and validation early stopping.
- The 3D Saliency view has an editable epoch-relative time control: a slider and numeric seconds input
  stay aligned to the plotted sample time.

### Changed

- Import, review, confirmation, and recipe handling were stabilized around the existing Command API,
  including clearer import-review decisions and recovery after advisory dataset updates.
- Epoch setup identifies time anchors by source semantics rather than exposing opaque event codes.
- The local Granite Assistant remains on the same bounded command workflow while its clarification and
  no-action behavior received targeted reliability improvements.

### Fixed

- BIDS Electrode Layout selection, replacement, readiness, and dialog presentation are more reliable
  across reviewed imports.
- Recipe saving no longer spuriously asks to review and save again when a non-decisive background
  publication arrives; a saved recipe can be reloaded safely in the same import session.
- Training settings, warnings, and 3D rendering controls no longer expose several observed overlap,
  clipping, duplicate-label, or stale-publication failures.

### Release boundary

- This is a manually accepted Desktop Workflow Stabilization source baseline, not a signed installer
  or a fixed 10-second import-latency SLA.
- Recipe JSON records source and label paths; it is not portable after those files are moved.
- The Assistant baseline is bounded at 22/24 product no-action and 6/7 clarification execution cases,
  not a 24/24 and 7/7 Stable promotion.
- Scientific model, training, saliency, and attribution validity certification remain outside this
  release claim.

## [0.8.0] - 2026-08-24

### Changed

- Saliency selection now distinguishes exact Fold and Evaluation-admitted Fold Set targets, shows
  uncomputed targets explicitly, and keeps older computed results available for deliberate review.
- Saliency Map class navigation, responsive settings, Spectrogram presentation, Topographic Map, and
  3D controls were consolidated for clearer all-class comparison and single-class inspection.
- The 3D view now uses epoch-relative time below the scene, a centered Saliency scale, contextual
  configuration actions, and one orientation widget across repeated renders.
- Blocking warnings and confirmations use the shared XBrainLab modal presentation, while detached
  Evaluation rendering no longer presents a misleading user-owned cancel action.

### Fixed

- Cancel Import and review recovery preserve staged label choices and observed event evidence without
  partially mutating product data.
- Repeated Training followed by Compute Saliency correctly admits the newest result without requiring
  an unchanged settings review or reusing stale Fold Set output.
- Saliency empty-state messaging, render publication, reset controls, class selectors, narrow layouts,
  and repeated 3D scene updates no longer overlap, duplicate controls, or publish intermediate scenes.

### Release boundary

- This is a manually accepted source/desktop workflow refresh, not a signed installer or a scientific
  validity certification for attribution results.
- Cross-platform CI protects source startup and lifecycle contracts; it does not replace native
  installer, arbitrary hardware, DPI, OpenGL, or dataset certification.
- Safety-zero-tolerance, arbitrary dataset/model support, and product 1.0 remain outside this release.

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
