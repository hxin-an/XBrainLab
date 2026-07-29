# Teacher Handoff Gate

- Source commit: `1623c5b9136bee0993a27dc89f496c598be6c2b8`
- Strict result: `PASS`
- Fixture profile: `10 groups / 277,106,963 bytes`

| Gate | Result | Duration |
| --- | --- | ---: |
| backend_timing_and_epoch | PASS | 38.095s |
| real_gui_workflows | PASS | 179.547s |

## Current UI Artifacts

- `openneuro-event-value-controls.png`
- `openneuro-match-labels-dialog.png`
- `openneuro-review-and-import.png`

## Claim Boundary

- This gate covers the pinned teacher fixture profile, backend timing/epoch handoff, and the real Qt five-step wizard paths.
- It does not replace human Windows DPI, remote-desktop, or teacher acceptance, and it does not certify unsupported clinical annotation sidecars.
