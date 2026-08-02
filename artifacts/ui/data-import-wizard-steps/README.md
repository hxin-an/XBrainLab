# Data Import Wizard Screenshots

status: tracked dirty checkpoint for visual review; not release-candidate evidence
generator: `scripts/dev/capture_data_import_wizard_steps.py`
environment: Qt xcb capture on a 1600x1400 Xvfb screen
supports: Data Import wizard step layout, Load Labels, Match Labels source/placement modes, Review and Import visual review
does_not_support: human Windows acceptance, full arbitrary BIDS compliance, scientific label semantics approval
next_human_or_runtime_gate: manual Windows click-through on representative EEG/label files before release approval

This folder keeps only canonical review images for the current wizard design.
Exploratory drafts and superseded discussion variants should not be kept here.

Generate final candidate evidence outside this tracked folder with:

```bash
HANDOFF_EVIDENCE_ROOT="/mnt/d/XBrainLabEvidence/$(git rev-parse HEAD)"
QT_QPA_PLATFORM=xcb xvfb-run -a -s '-screen 0 1600x1400x24' \
  poetry run python scripts/dev/capture_data_import_wizard_steps.py \
  --output-dir "$HANDOFF_EVIDENCE_ROOT/ui/data-import-wizard-steps"
```

Validate this tracked checkpoint without rewriting it:

```bash
QT_QPA_PLATFORM=offscreen poetry run python \
  scripts/dev/capture_data_import_wizard_steps.py \
  --output-dir artifacts/ui/data-import-wizard-steps --validate-only
```

- `01-choose-eeg-data.png`
- `02-load-labels-many.png`
- `03-review-metadata.png`
- `04-match-labels-internal-advanced-760px.png`
- `04-match-labels-final-loaded-label-files.png`
- `04-match-labels-bids-events.png`
- `04-match-labels-conversion-fallback.png`
- `04-match-labels-conversion-table-format-dialog.png`
- `05-review-and-import.png`
- `05-review-and-import-report.png`

Step 4 intentionally has multiple images because the product has different label
source and fallback modes to review: labels inside EEG files, loaded label
files, strict BIDS events.tsv, and unsupported custom label formats.

Loaded label file placement-mode review images live under
`match-label-placement-modes/`:

- `eeg-event-order-full.png`
- `label-time-full.png`
- `label-interval-full.png`
- `label-event-code-full.png`
