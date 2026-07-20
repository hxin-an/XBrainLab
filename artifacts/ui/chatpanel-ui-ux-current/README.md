# ChatPanel UI/UX Walkthrough Gate

This directory is generated from real Qt widgets. It includes focused ChatPanel states and a composed `MainWindow` / `QDockWidget` walkthrough. Visual acceptance remains a separate reviewer decision.

## Replay

```bash
QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_ui_ux_walkthrough.py
```

- machine gate: `passed`
- source fingerprint: `6d126ee823fce3711c432c1c752d327ad0dc5fef6afb02e6d7e24f046321689e`
- source stable during capture: `True`
- source fingerprint at start / completion: `6d126ee823fce3711c432c1c752d327ad0dc5fef6afb02e6d7e24f046321689e` / `6d126ee823fce3711c432c1c752d327ad0dc5fef6afb02e6d7e24f046321689e`
- fingerprinted source files: `31`
- Qt platform: `offscreen`
- visual reviewer verdict: `not adjudicated by this script`
- native display scaling observed: `false`

## Screens

| Screenshot | Logical / rendered pixel size | States | Checks |
| --- | --- | --- | --- |
| `desktop-conversation-states.png` | 460 x 900 / 460 x 900 | user, assistant, tool_result, attention, clarification, cancelled | PASS |
| `narrow-conversation-states.png` | 320 x 760 / 320 x 760 | user, tool_result, attention, cancelled | PASS |
| `desktop-runtime-loading.png` | 460 x 680 / 460 x 680 | runtime / activity state | PASS |
| `narrow-runtime-unavailable.png` | 320 x 680 / 320 x 680 | runtime / activity state | PASS |
| `narrow-history-restored-audit.png` | 320 x 680 / 320 x 680 | user, error | PASS |
| `narrow-cancellable-progress.png` | 320 x 680 / 320 x 680 | user | PASS |
| `narrow-stopping-progress.png` | 320 x 680 / 320 x 680 | user | PASS |
| `narrow-command-progress.png` | 320 x 680 / 320 x 680 | user | PASS |
| `narrow-error-action.png` | 320 x 680 / 320 x 680 | user, error | PASS |
| `narrow-setting-change-confirmation.png` | 320 x 680 / 320 x 680 | user | PASS |
| `narrow-setting-change-confirmation-max-content.png` | 320 x 680 / 320 x 680 | user | PASS |
| `pixmap-scaled-narrow.png` | 320 x 760 / 480 x 1140 | user, tool_result, attention, cancelled | PASS |
| `responsive-320-idle.png` | 320 x 650 / 320 x 650 | runtime / activity state | PASS |
| `responsive-320-long-clarification-action-520.png` | 320 x 520 / 320 x 520 | user, clarification | PASS |
| `responsive-320-long-clarification-action-650.png` | 320 x 650 / 320 x 650 | user, clarification | PASS |
| `responsive-320-processing-stop.png` | 320 x 650 / 320 x 650 | user | PASS |
| `responsive-320-runtime-unavailable.png` | 320 x 650 / 320 x 650 | runtime / activity state | PASS |
| `responsive-760-idle.png` | 760 x 650 / 760 x 650 | runtime / activity state | PASS |
| `responsive-760-long-clarification-action.png` | 760 x 650 / 760 x 650 | user, clarification | PASS |
| `responsive-760-processing-stop.png` | 760 x 650 / 760 x 650 | user | PASS |
| `responsive-760-runtime-unavailable.png` | 760 x 650 / 760 x 650 | runtime / activity state | PASS |
| `responsive-1280-idle.png` | 1280 x 650 / 1280 x 650 | runtime / activity state | PASS |
| `responsive-1280-long-clarification-action.png` | 1280 x 650 / 1280 x 650 | user, clarification | PASS |
| `responsive-1280-processing-stop.png` | 1280 x 650 / 1280 x 650 | user | PASS |
| `responsive-1280-runtime-unavailable.png` | 1280 x 650 / 1280 x 650 | runtime / activity state | PASS |
| `main-window-dock-320-action-click.png` | 1180 x 760 / 1180 x 760 | user, clarification, clarification | PASS |
| `main-window-dock-320-stopping.png` | 1180 x 760 / 1180 x 760 | user, clarification, clarification | PASS |
| `main-window-dock-320-command-running.png` | 1180 x 760 / 1180 x 760 | user, clarification, clarification | PASS |

## First Paint

The standalone ChatPanel and the real MainWindow dock are both sampled inside their first 320 px ChatPanel paint event, before the layout-settle helper runs. The mode selector must already be visible while its controls, composer, and Send action remain disabled for the idle runtime.

- first-paint contract passed: `True`
- standalone frame: `first-paint-320-standalone.png`
- real dock frame: `first-paint-320-real-dock.png`

## Training Metric Transition

A real `MetricTab` records the pre-first-epoch empty state, then applies epoch 1 through `update_plot()` and records the first train/validation series frame.

- transition passed: `True`
- empty frame: `training-metric-pre-first-epoch.png`
- first-data frame: `training-metric-first-data.png`

## Teardown

The composed walkthrough binds a dedicated `AssistantCommandThread`, requests `AgentManager.close()`, and observes dispatcher cleanup, runtime cleanup, QThread completion, GUI heartbeat continuity, and close-call latency through Qt signals and an event loop. It does not call `QThread.wait()` on the GUI thread.

- teardown passed: `True`
- manager close finished: `True`
- dedicated QThread finished: `True`
- initial close-call latency: `3.452 ms`
- GUI heartbeat count / max gap: `14` / `5.777 ms`

## Interaction Coverage

The composed walkthrough uses the real `MainWindow`, `AgentManager`, `QDockWidget`, and `ChatPanel`. It establishes a 320 px ChatPanel width, proves a response action restored from serialized history is inert, then clicks a correlated live-turn action to open Dataset. It then clicks Stop while the typed state is cancellable, proves late activity for that turn remains latched at Stopping until the matching terminal event, and records a new-turn Application command state where Stop is unavailable.

## Render Readiness

Every saved frame must pass the pixel-content gate twice consecutively. QPixmap output is normalized to a standard RGB PNG before inspection. The composed MainWindow frames additionally require painted main-shell, assistant transcript, and primary-action regions; visible activity cards are checked separately. Restored actions must remain inert, and the live action is checked in its own painted region before the real click. Solid or shell-only captures fail the gate.

## Render Scaling

`pixmap-scaled-narrow.png` uses synthetic pixmap scaling via `QPixmap.setDevicePixelRatio(1.5)`. It checks scaled rendering output dimensions only. It does not demonstrate native display scaling, Windows DPI behavior, monitor transitions, or operating-system compositor behavior.

## Claim Boundary

Linux/Qt offscreen rendering and geometry evidence, including a real MainWindow/QDockWidget composition. The 1.5x image uses synthetic QPixmap device-ratio rendering and does not demonstrate native display scaling. This gate does not prove Windows launcher acceptance, Windows native DPI, multi-monitor behavior, local-model correctness, long-session behavior, or full-product completion.
