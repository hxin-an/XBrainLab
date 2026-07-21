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
- training output dir: `artifacts/tmp/review-preprocess-polish-visualization-training`
- dataset preparation ok: `True`
- finished runs: `1`
- metrics available: `True`
- saliency available: `True`
- ready screenshot: `artifacts/ui/review-preprocess-polish/visualization-render/visualization-render-saliency-map-9d16ebaacaad.png`
- elapsed seconds: `<runtime-dependent>`
- uncaught exceptions: `0`

## Rendered Tabs

### Saliency Map

- status: `ok`
- screenshot: `artifacts/ui/review-preprocess-polish/visualization-render/visualization-render-saliency-map-9d16ebaacaad.png`
- screenshot SHA-256: `9d16ebaacaad404da1cfdcf38654c8b65bf6c986a844c0bfa5272f98b15310a9`
- axes count: `3`
- image count: `4`
- scientific context: Grouped by true class label · Mean across evaluated epochs
- error visible: `False`
- canvas visible: `True`
- artist layout: `inside canvas`
- canvas color count: `921`
- canvas chromatic fraction: `0.387867`

### Spectrogram

- status: `ok`
- screenshot: `artifacts/ui/review-preprocess-polish/visualization-render/visualization-render-spectrogram-43f54d0b2656.png`
- screenshot SHA-256: `43f54d0b2656c3917695e6ae35549ba669211ede1549154d2da5ebc4af3694a3`
- axes count: `3`
- image count: `4`
- scientific context: Grouped by true class label · Mean magnitude across evaluated epochs and channels
- error visible: `False`
- canvas visible: `True`
- artist layout: `inside canvas`
- canvas color count: `837`
- canvas chromatic fraction: `0.434342`

### Topographic Map

- status: `ok`
- screenshot: `artifacts/ui/review-preprocess-polish/visualization-render/visualization-render-topographic-map-b2882ef8566a.png`
- screenshot SHA-256: `b2882ef8566a716dcece367d3aa0590d089d0e056585d747b25d1c6b6bfd0da4`
- axes count: `3`
- image count: `8`
- scientific context: Grouped by true class label · Mean across evaluated epochs and time
- error visible: `False`
- canvas visible: `True`
- artist layout: `inside canvas`
- canvas color count: `4110`
- canvas chromatic fraction: `0.074664`

## Blocked Tabs

### 3D Plot

- status: `ok`
- screenshot: `artifacts/ui/review-preprocess-polish/visualization-render/visualization-render-3d-blocked-7a0c8cfacb78.png`
- screenshot SHA-256: `7a0c8cfacb78489d77334fdbef54dcf9d9a44f8990d3433f3cb32dad1a497191`
- plotter created: `False`
- terminal outcome: `blocked`
- blocked reason: 3D rendering requires an interactive OpenGL desktop session. Use the desktop launcher, or switch to Saliency Map, Spectrogram, or Topographic Map in this headless environment.
- message chromatic fraction: `0.054237`

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
