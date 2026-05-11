# Visualization Render Walkthrough

- status: `passed`
- failure reason: none
- source path: `/tmp/xbrainlab_chatpanel_training_completion/training_completion_raw.fif`
- training output dir: `/tmp/xbrainlab-visualization-render-output`
- dataset preparation ok: `True`
- finished runs: `1`
- metrics available: `True`
- saliency available: `True`
- ready screenshot: `artifacts/ui/visualization-render/visualization-render-ready.png`
- elapsed seconds: `7.164`

## Rendered Tabs

### Saliency Map

- status: `ok`
- screenshot: `artifacts/ui/visualization-render/visualization-render-saliency-map.png`
- axes count: `3`
- image count: `3`
- error visible: `False`
- canvas visible: `True`

### Spectrogram

- status: `ok`
- screenshot: `artifacts/ui/visualization-render/visualization-render-spectrogram.png`
- axes count: `3`
- image count: `3`
- error visible: `False`
- canvas visible: `True`

### Topographic Map

- status: `ok`
- screenshot: `artifacts/ui/visualization-render/visualization-render-topographic-map.png`
- axes count: `3`
- image count: `4`
- error visible: `False`
- canvas visible: `True`

## Blocked Tabs

### 3D Plot

- status: `ok`
- screenshot: `artifacts/ui/visualization-render/visualization-render-3d-blocked.png`
- plotter created: `False`
- blocked reason: 3D rendering requires an interactive OpenGL desktop session. Use the desktop launcher, or switch to Saliency Map, Spectrogram, or Topographic Map in this headless environment.

## UI State

- current panel: `Visualization`
- plan: `Fold 1 (EEGNet)`
- run: `Run 1`
- method: `Gradient`
- montage available: `True`

## Claim Boundary

- Supports true MainWindow VisualizationPanel Matplotlib saliency renders.
- Supports a user-facing 3D blocked reason in headless/offscreen runtime.
- Does not support interactive 3D render or Windows human click-through.
