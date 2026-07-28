# App Polish Screenshots

status: generated focused UI review evidence
generator: `scripts/dev/capture_ui_polish_surfaces.py`
environment: PyQt offscreen capture
supports: current visual state for adaptive assistant setup, active-turn, and runtime recovery surfaces, plus model selection, data splitting, and evaluation metrics table polish
does_not_support: end-to-end training quality, human desktop acceptance, or long-running runtime behavior
next_human_or_runtime_gate: open the same dialogs in the Windows desktop app during manual acceptance

Focused current screenshots for manual review of surfaces that are not fully represented by the Data Import wizard artifacts. Regenerate the complete set with:

```bash
QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_ui_polish_surfaces.py
```

Regenerate only the narrow assistant evidence with:

```bash
QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_ui_polish_surfaces.py --only assistant-setup-required-narrow.png --only assistant-active-turn-narrow.png --only assistant-loading.png --only assistant-failed.png --only assistant-recovery-loading.png
```

- `model-selection-dialog.png`
- `training-setting-dialog.png`
- `preprocess-rereference-dialog.png`
- `preprocess-epoching-internal-events-dialog.png`
- `preprocess-epoching-bids-interval-duration-dialog.png`
- `data-splitting-dialog.png` (752 x 470 scroll fallback)
- `data-splitting-dialog-narrow.png` (752 x 700 full reflow)
- `data-splitting-preview-dialog.png`
- `assistant-setup-required-narrow.png` (320 x 650, setup-required recovery)
- `assistant-active-turn-narrow.png` (420 x 650, adaptive active-turn processing)
- `assistant-loading.png` (420 x 650, inline runtime loading)
- `assistant-failed.png` (420 x 650, unavailable recovery action)
- `assistant-recovery-loading.png` (420 x 650, retry in progress)
- `saliency-setting-dialog.png`
- `saliency-setting-single-method.png`
- `saliency-setting-empty-state.png`
- `set-montage-dialog.png`
- `evaluation-controls-panel.png`
- `evaluation-metrics-table.png`
- `training-history-few-rows.png` (completed runs; Start enabled)
- `training-history-many-rows.png` (active run; Stop enabled)
