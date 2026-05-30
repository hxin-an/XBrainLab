# Visualization Render Walkthrough

- artifact status: `current release-candidate visualization evidence`
- generator: `scripts/dev/capture_visualization_render_walkthrough.py`
- environment: Qt offscreen VisualizationPanel capture with PYVISTA_OFF_SCREEN
- supports: MainWindow VisualizationPanel 2D saliency renders and headless 3D blocked state
- does_not_support: interactive 3D render or human Windows click-through acceptance
- next_human_or_runtime_gate: manual desktop visualization click-through with an interactive OpenGL session

- status: `passed`
- failure reason: none
- source path: `/tmp/xbrainlab_chatpanel_training_completion/training_completion_raw.fif`
- training output dir: `/tmp/xbrainlab-visualization-render-output`
- dataset preparation ok: `True`
- finished runs: `1`
- metrics available: `True`
- saliency available: `True`
- ready screenshot: `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual/artifacts/ui/visualization-render/visualization-render-saliency-map.png`
- elapsed seconds: `8.703`
- uncaught exceptions: `0`

## Rendered Tabs

### Saliency Map

- status: `ok`
- screenshot: `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual/artifacts/ui/visualization-render/visualization-render-saliency-map.png`
- axes count: `2`
- image count: `3`
- error visible: `False`
- canvas visible: `True`

### Spectrogram

- status: `ok`
- screenshot: `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual/artifacts/ui/visualization-render/visualization-render-spectrogram.png`
- axes count: `2`
- image count: `3`
- error visible: `False`
- canvas visible: `True`

### Topographic Map

- status: `ok`
- screenshot: `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual/artifacts/ui/visualization-render/visualization-render-topographic-map.png`
- axes count: `2`
- image count: `4`
- error visible: `False`
- canvas visible: `True`

## Blocked Tabs

### 3D Plot

- status: `ok`
- screenshot: `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual/artifacts/ui/visualization-render/visualization-render-3d-blocked.png`
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
- Supports user-facing 3D blocked reason in headless/offscreen runtime.
- Does not support interactive 3D render.
- Does not support Windows human click-through.
