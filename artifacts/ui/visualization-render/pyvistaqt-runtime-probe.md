# PyVistaQt Runtime Probe

- status: `blocked`
- claim boundary: Interactive PyVistaQt runtime probe only; not a full XBrainLab 3D saliency render or human desktop click-through.
- timeout seconds: `60`

## Environment

- `DISPLAY`: `:0`
- `WAYLAND_DISPLAY`: `wayland-0`
- `QT_QPA_PLATFORM`: ``
- `PYVISTA_OFF_SCREEN`: ``

## Checks

- `returncode_zero`: `False`
- `plotter_created_stdout`: `False`
- `stdout_image_exists`: `False`
- `screenshot_exists`: `False`
- `bad_window_error`: `True`

## Output

### stdout

```text
(empty)
```

### stderr

```text
X Error of failed request:  BadWindow (invalid Window parameter)
  Major opcode of failed request:  12 (X_ConfigureWindow)
  Resource id in failed request:  0x2ec72800
  Serial number of failed request:  7
  Current serial number in output stream:  8
```
