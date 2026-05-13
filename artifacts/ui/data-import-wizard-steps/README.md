# Data Import Wizard Screenshots

This folder keeps the smallest current screenshot set needed to review the
Data Import wizard shape. Exploratory drafts, status variants, and superseded
discussion images should stay in git history instead of the current tree.

- `01-choose-eeg-data.png`
- `02-load-labels-many.png`
- `03-review-metadata-smart-parse.png`
- `04-match-labels-internal-eeg-labels.png`
- `match-label-placement-modes/eeg-event-order-full.png`
- `match-label-placement-modes/label-time-full.png`
- `match-label-placement-modes/label-interval-full.png`
- `match-label-placement-modes/label-event-code-full.png`
- `05-review-and-import-normal.png`

Step 4 intentionally keeps the four placement panels because they represent
different backend interpretation choices. Other Match Labels discussion states
can be regenerated when a UX review specifically needs them.

The `match-label-placement-modes/` images are current review evidence for the
four supported loaded-label placement panels.

Regenerate the placement panel artifacts with:

```bash
QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_import_match_label_placement_modes.py
```
