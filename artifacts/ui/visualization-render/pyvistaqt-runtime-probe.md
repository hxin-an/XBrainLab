# PyVistaQt Runtime Probe

- status: `passed`
- claim boundary: Interactive PyVistaQt runtime probe only; not a full XBrainLab 3D saliency render or human desktop click-through.
- timeout seconds: `20`

## Environment

- `DISPLAY`: `:0`
- `WAYLAND_DISPLAY`: `wayland-0`
- `QT_QPA_PLATFORM`: `xcb`
- `PYVISTA_OFF_SCREEN`: ``

## Checks

- `returncode_zero`: `True`
- `plotter_created_stdout`: `True`
- `stdout_image_exists`: `True`
- `screenshot_exists`: `True`
- `bad_window_error`: `False`

## Output

### stdout

```text
plotter_created=True
image_exists=True
```

### stderr

```text
(empty)
```
