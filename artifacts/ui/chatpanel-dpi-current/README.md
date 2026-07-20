# ChatPanel Qt Scale Gate

- status: `passed`
- replay: `poetry run python scripts/dev/run_chatpanel_ui_dpi_gate.py`

| QT scale | Observed DPR | Status | Screenshots |
| ---: | ---: | --- | --- |
| 1 | 1.0 | passed | `scale-100-first-paint-320-real-dock.png`, `scale-100-responsive-320-idle.png`, `scale-100-narrow-setting-change-confirmation-max-content.png` |
| 1.25 | 1.25 | passed | `scale-125-first-paint-320-real-dock.png`, `scale-125-responsive-320-idle.png`, `scale-125-narrow-setting-change-confirmation-max-content.png` |
| 1.5 | 1.5 | passed | `scale-150-first-paint-320-real-dock.png`, `scale-150-responsive-320-idle.png`, `scale-150-narrow-setting-change-confirmation-max-content.png` |

## Claim Boundary

This gate runs Linux Qt offscreen subprocesses with explicit QT_SCALE_FACTOR values. It validates device-pixel-ratio observation, layout, text-fit, and interaction contracts at those configured scales. It does not replace Windows native DPI, multi-monitor, compositor, or human click-through acceptance.
