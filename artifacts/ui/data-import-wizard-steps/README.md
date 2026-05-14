# Data Import Wizard Screenshots

This folder keeps the canonical current screenshot set needed to review the
Data Import wizard shape. Exploratory drafts and superseded discussion images
should stay in git history instead of the current tree.

- `01-choose-eeg-data.png`
- `02-load-labels-empty.png`
- `02-load-labels-auto-detected.png`
- `02-load-labels-user-added.png`
- `02-load-labels-duplicate-removal.png`
- `02-load-labels-many.png`
- `03-review-metadata-smart-parse.png`
- `04-match-labels-internal-eeg-labels.png`
- `04-match-labels-bids-eeg-events.png`
- `04-match-labels-conversion-fallback.png`
- `04-match-labels-conversion-examples.png`
- `match-label-placement-modes/eeg-event-order-full.png`
- `match-label-placement-modes/label-time-full.png`
- `match-label-placement-modes/label-interval-full.png`
- `match-label-placement-modes/label-event-code-full.png`
- `05-review-and-import-normal.png`
- `05-review-and-import-needs-review.png`
- `05-review-and-import-blocked.png`
- `05-review-and-import-bids-ready.png`
- `epoch-after-bids-import.png`
- `epoch-handoff-evidence.json`

Step 4 intentionally keeps multiple images because the product has distinct
label source and placement states: labels inside EEG files, loaded label files,
BIDS-EEG events, and blocked conversion fallback.

The `match-label-placement-modes/` images are current review evidence for the
four supported loaded-label placement panels.

`epoch-handoff-evidence.json` is generated through
`ApplicationService.apply_interpretation` on temporary product fixtures. It is
not a hand-written screenshot companion; it records BIDS selected scope,
sidecar evidence, label import result, saved recipe data, and the state snapshot
handoff that the Epoch step can consume.

Regenerate these artifacts with:

```bash
QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_import_wizard_steps.py
QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_import_match_label_placement_modes.py
```
