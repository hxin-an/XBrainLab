# App Polish Screenshots

status: generated focused UI review evidence
generator: `scripts/dev/capture_ui_polish_surfaces.py`
environment: PyQt offscreen capture
supports: current visual state for assistant single-step/Workflow narrow surfaces, model selection, data splitting, and evaluation metrics table polish
does_not_support: end-to-end training quality, human desktop acceptance, or long-running runtime behavior
next_human_or_runtime_gate: open the same dialogs in the Windows desktop app during manual acceptance

Focused current screenshots for manual review of surfaces that are not fully represented by the Data Import wizard artifacts. Regenerate the complete set with:

```bash
QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_ui_polish_surfaces.py
```

Regenerate only the narrow assistant evidence with:

```bash
QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_ui_polish_surfaces.py --only assistant-ask-narrow.png --only assistant-workflow-narrow.png
```

- `model-selection-dialog.png`
- `training-setting-dialog.png`
- `preprocess-rereference-dialog.png`
- `preprocess-epoching-dialog.png`
- `data-splitting-dialog.png` (752 x 470 scroll fallback)
- `data-splitting-dialog-narrow.png` (752 x 700 full reflow)
- `data-splitting-preview-dialog.png`
- `assistant-ask-narrow.png` (340 x 650, current single-step mode)
- `assistant-workflow-narrow.png` (340 x 650)
- `saliency-setting-dialog.png`
- `saliency-setting-single-method.png`
- `saliency-setting-empty-state.png`
- `set-montage-dialog.png`
- `evaluation-controls-panel.png`
- `evaluation-metrics-table.png`
