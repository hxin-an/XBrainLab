# Data Import Wizard Screenshots

status: current release-candidate UI evidence
generator: `scripts/dev/capture_data_import_wizard_steps.py`
environment: Qt offscreen desktop capture on `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual`
supports: Data Import wizard step layout, Load Labels, Match Labels source/placement modes, Review and Import visual review
does_not_support: human Windows acceptance, full arbitrary BIDS compliance, scientific label semantics approval
next_human_or_runtime_gate: manual Windows click-through on representative EEG/label files before release approval

This folder keeps only canonical review images for the current wizard design.
Exploratory drafts and superseded discussion variants should not be kept here.

- `01-choose-eeg-data.png`
- `02-load-labels-many.png`
- `03-review-metadata.png`
- `04-match-labels-internal-suggested-events-full.png`
- `04-match-labels-final-loaded-label-files.png`
- `04-match-labels-bids-events.png`
- `04-match-labels-conversion-fallback.png`
- `04-match-labels-conversion-table-format-dialog.png`
- `05-review-and-import.png`

Step 4 intentionally has multiple images because the product has different label
source and fallback modes to review: labels inside EEG files, loaded label
files, BIDS-like events, and unsupported custom label formats.

Loaded label file placement-mode review images live under
`match-label-placement-modes/`:

- `eeg-event-order-full.png`
- `label-time-full.png`
- `label-interval-full.png`
- `label-event-code-full.png`
