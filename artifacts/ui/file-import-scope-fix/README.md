# Explicit File Import Scope Evidence

This artifact set validates the 2026-07-29 explicit file-selection regression fix.

- `three-gdf-exact-file-scope.png`: the checked-in A01T/A02T/A03T selection opens
  the wizard with exactly three EEG files and three matching label carriers.
- `standard-dialog-buttons.png`: standard error-dialog OK presentation after the
  application-wide dialog button policy; no Return/Enter glyph is shown.
- `openneuro-*.png`: visible BIDS workflow surfaces captured while the required
  multi-source Data Import acceptance suite ran.

The captures use Qt's offscreen platform. Windows/WSLg click-through remains a
separate final acceptance boundary.
