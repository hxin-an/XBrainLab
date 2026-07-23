# Assistant Presentation Evidence

Current Linux/Qt offscreen evidence for the Agent Panel presentation checkpoint.
The selected images cover loading, empty, conversation, confirmation, error,
narrow-width, Settings, constrained-height, and 150% Qt scale states.

## Validation

- focused ChatPanel gate: passed, source fingerprint
  `dc19918c555fbcc9ea659d7cea8117c254c02bc63f2af2c9a39fdd0f69ed2f71`
- human-like product walkthrough: `42/42` phases, `44` required screenshots,
  resource smoke passed, source fingerprint
  `4b5771bf1631a4281953cdd26869e7b60019d158b04664feab40141f6d897834`
- Qt scale gate: passed at `100%`, `125%`, and `150%`
- Settings constrained-height probe: expanded dialog `520 x 552`, fixed footer
  Save bottom at `y=535`, body scroll maximum `166`

Machine-readable focused and DPI details are in `focused-walkthrough.json` and
`dpi-gate.json`. The compact human-readable product replay is in
`human-like-walkthrough.md`; the full JSON replay is intentionally regenerated
on demand because it exceeds the repository artifact-size limit.

## Replay

```bash
QT_QPA_PLATFORM=offscreen poetry run python \
  scripts/dev/capture_chatpanel_ui_ux_walkthrough.py

QT_QPA_PLATFORM=offscreen poetry run python \
  scripts/dev/run_chatpanel_ui_dpi_gate.py

QT_QPA_PLATFORM=offscreen poetry run python \
  scripts/dev/capture_human_like_product_walkthrough.py
```

## Claim Boundary

These artifacts demonstrate current-source Linux/Qt layout, text-fit, interaction,
and product-surface state coverage. They do not replace Windows native DPI,
multi-monitor, long real local-model sessions, or human desktop acceptance.
