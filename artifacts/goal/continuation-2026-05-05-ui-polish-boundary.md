# XBrainLab Product Completion Continuation - 2026-05-05 UI Polish Boundary

Use this as the next-run handoff for the active product-completion goal. Do not
mark Goal 1 product-complete while the blockers below remain.

## Latest Local Commits

The latest validated commits at this handoff point are:

```text
de796fe ui: refresh aggregate info through service
9b4fae6 ui: route visualization observer refresh
4d10496 docs: add ui polish continuation
ee39fd6 ui: normalize montage command positions
fd95cf8 ui: neutralize dataset channel action
172d871 ui: humanize legacy fallback refusal
5e1efb8 eval: gate full local runs on resource preflight
f8f47ba ui: route training observer lifecycle
```

Do not push. Preserve the user-owned dirty files:

```text
 M .agents/skills/README.md
 M .vscode/settings.json
 M settings.json
?? .agents/skills/clean-code-reviewer/
?? .agents/skills/data-interpretation-reviewer/
?? .agents/skills/mcp-adapter-reviewer/
?? .agents/skills/performance-resource-reviewer/
?? .agents/skills/release-packaging-reviewer/
?? .agents/skills/security-privacy-reviewer/
?? .agents/skills/thesis-evidence-reviewer/
?? .agents/skills/ui-product-reviewer/
```

## What Changed In The Latest Slice

- Dataset sidebar `Channel Selection` is now a neutral sidebar action, not
  success-green. It modifies data, so green was misleading before a success
  result exists.
- `artifacts/ui/human-like-walkthrough/` was refreshed with Qt offscreen. The
  summary reports `passed`, `26 / 26` phases, `20` screenshots, UI quality checks
  passed, and resource smoke passed. This is automated PyQt evidence, not human
  Windows desktop acceptance.
- AgentManager and Visualization sidebar now share
  `XBrainLab/ui/montage_positions.py::normalize_montage_positions()`. Confirmed
  montage positions are normalized into JSON-safe float tuples before
  `ApplyMontageCommand`; malformed coordinate vectors are blocked before
  ApplicationService.
- `montage_changed` / `saliency_changed` now route through
  `refresh_coordinator` and are owned by VisualizationPanel. Helper/secondary
  contexts no longer refresh the wrong panel for visualization observer events.
- `MainWindow.update_info_panel()` now delegates to
  `InfoPanelService.notify_all()` in product MainWindow contexts. Direct
  `info_panel.update_info()` remains only as an injected / legacy fallback.
- Docs updated:
  `docs/current.md`, `docs/architecture/ui.md`, `docs/planning/now.md`,
  `docs/planning/roadmap.md`, `docs/validation/README.md`,
  `docs/records/implementation_log.md`, and `docs/records/worklog.md`.

## Validation Just Run

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_dataset_sidebar.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_agent_manager_coverage.py \
  tests/unit/ui/visualization/test_control_sidebar.py -q
# 31 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_refresh_coordinator.py \
  tests/unit/ui/test_panel_event_bridges.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  tests/unit/ui/test_visualization_panel_redesign.py -q
# 61 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_main_window_sync.py \
  tests/unit/ui/test_refresh_coordinator.py \
  tests/unit/ui/components/test_info_panel_service.py -q
# 36 passed

git diff --check
poetry run ruff check .
poetry run ruff format --check XBrainLab/ui/panels/dataset/sidebar.py \
  tests/unit/ui/dataset/test_dataset_sidebar.py
poetry run python tests/architecture_compliance.py
poetry run basedpyright
poetry run mkdocs build --strict
```

`mkdocs build --strict` passed with the existing MkDocs Material 2.0 advisory
banner.

## Eval Policy Reminder

Do not run full primary/fallback x3 local tool-call eval for routine slices.

- Fast dev gate: deterministic, changed/failed cases only, repeat `1`, no
  fallback model.
- Candidate gate: primary model, affected families, repeat `1` or `2`.
- Release/thesis gate only: deterministic full suite, primary full suite x3,
  fallback full suite x3, dashboard refresh.

Before any local model eval, run resource preflight and check `nvidia-smi`. Do
not start full fallback x3 if VRAM is already near full.

## Remaining Product Blockers

- UI refresh remains partially mixed: command-result coordinator baseline plus
  observer/manual/tab-switch/event-specific refresh. Continue
  `UI Command Refresh Coordinator + Controller Fallback Audit`.
- Product runtime controller fallback should remain mock / legacy-only; keep
  auditing any remaining UI mutating paths.
- Data Interpretation is stronger but not final: mature embedded label editor,
  raw trigger selector, complex GDF / MAT anchor reconciliation, XDF / LSL full
  parser, real-data manual certification, and recipe diff/review UX remain.
- Label import still exists as service-backed compatibility UI; do not let it
  become the primary data-entry mental model.
- Human Windows desktop acceptance is still not done: launcher click-through,
  dual monitor / DPI behavior, and long real local-model desktop session.
- Interactive desktop 3D / PyVista render remains not fully accepted.
- Long autonomous ChatPanel workflow, UI-routing render, and full recovery
  behavior remain open.
- HTTP MCP transport and long-running MCP job progress/cancel/recovery remain
  open.

## Recommended Next Slice

Continue the architecture/product cleanup with a small validated slice:

1. Audit one remaining observer/manual refresh path and route it through the
   refresh coordinator, with focused tests on changed-state -> panel/sidebar /
   assistant refresh. The next useful sub-area is high-frequency / event-specific
   training refresh ownership or remaining manual refresh helpers.
2. Or advance the Data Interpretation mature wizard by adding a focused
   user-facing editor capability that reduces reliance on post-load label import
   compatibility.
3. Do not update formal tool-call benchmark claims unless intentionally running
   the release/thesis eval gate.
