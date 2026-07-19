# Visualization Render Walkthrough

- artifact status: `current release-candidate visualization evidence`
- generator: `scripts/dev/capture_visualization_render_walkthrough.py`
- environment: Qt offscreen noninteractive VisualizationPanel capture
- supports: MainWindow VisualizationPanel 2D saliency renders and the user-facing 3D blocked state
- does_not_support: interactive 3D render or human Windows click-through acceptance
- next_human_or_runtime_gate: repeat this walkthrough in an interactive XCB/OpenGL runtime
- Qt platform: `offscreen`
- expected 3D outcome: `blocked`

- status: `passed`
- failure reason: none
- source path: `/tmp/xbrainlab_chatpanel_training_completion/training_completion_raw.fif`
- training output dir: `/mnt/d/workspace_v2/tmp/xbrainlab-visualization-render-output`
- dataset preparation ok: `True`
- finished runs: `1`
- metrics available: `True`
- saliency available: `True`
- ready screenshot: `artifacts/ui/visualization-render/visualization-render-saliency-map-867b9ef05deb.png`
- elapsed seconds: `<runtime-dependent>`
- uncaught exceptions: `0`

## Rendered Tabs

### Saliency Map

- status: `ok`
- screenshot: `artifacts/ui/visualization-render/visualization-render-saliency-map-867b9ef05deb.png`
- screenshot SHA-256: `867b9ef05debcfe7a36805cde8515d8f1222449641df543f94bee96818d84a49`
- axes count: `3`
- image count: `4`
- scientific context: Grouped by true class label · Mean across evaluated epochs
- error visible: `False`
- canvas visible: `True`
- artist layout: `inside canvas`
- canvas color count: `939`
- canvas chromatic fraction: `0.388548`

### Spectrogram

- status: `ok`
- screenshot: `artifacts/ui/visualization-render/visualization-render-spectrogram-e0b39a14dc06.png`
- screenshot SHA-256: `e0b39a14dc064f5e3ebe0a68801d0aca42c736ed0888b72c8ab6e8a16dd7a6d8`
- axes count: `3`
- image count: `4`
- scientific context: Grouped by true class label · Mean magnitude across evaluated epochs and channels
- error visible: `False`
- canvas visible: `True`
- artist layout: `inside canvas`
- canvas color count: `775`
- canvas chromatic fraction: `0.342008`

### Topographic Map

- status: `ok`
- screenshot: `artifacts/ui/visualization-render/visualization-render-topographic-map-f839b79e33c6.png`
- screenshot SHA-256: `f839b79e33c6262b5f282167b04878b6bdfec81deb1fa996329b12939f1bcb79`
- axes count: `3`
- image count: `8`
- scientific context: Grouped by true class label · Mean across evaluated epochs and time
- error visible: `False`
- canvas visible: `True`
- artist layout: `inside canvas`
- canvas color count: `4486`
- canvas chromatic fraction: `0.074207`

## Blocked Tabs

### 3D Plot

- status: `ok`
- screenshot: `artifacts/ui/visualization-render/visualization-render-3d-blocked-718c8e796acc.png`
- screenshot SHA-256: `718c8e796acce934babd97a42b1c8fef1c2db9dd8f5cc9019791f8824426dfbe`
- plotter created: `False`
- terminal outcome: `blocked`
- blocked reason: 3D rendering requires an interactive OpenGL desktop session. Use the desktop launcher, or switch to Saliency Map, Spectrogram, or Topographic Map in this headless environment.
- message chromatic fraction: `0.057147`

## UI State

- current panel: `Visualization`
- plan: `Fold 1 (EEGNet)`
- run: `Run 1`
- method: `Gradient`
- montage available: `True`

## Claim Boundary

- Supports true MainWindow VisualizationPanel Matplotlib saliency renders.
- Supports user-facing 3D blocked reason in headless/offscreen runtime.
- Does not support interactive 3D render.
- Does not support Windows human click-through.
