# Changelog

Important user-visible changes are recorded here. Detailed development history remains available in
Git and merged pull requests.

## [Unreleased]

No user-visible changes are queued after the desktop baseline.

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
