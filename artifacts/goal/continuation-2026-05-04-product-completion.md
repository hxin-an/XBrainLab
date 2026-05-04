# XBrainLab Product Completion Continuation

Date: `2026-05-04`

Use this after usage refresh. Continue from active repo:

```text
/mnt/d/workspace_v2/projects/lab/XBrainLab
```

Latest usage-refresh handoff:

```text
artifacts/goal/handoff-2026-05-04-usage-refresh.md
```

## Hard Boundaries

- Do not push.
- Do not touch / revert `.vscode/settings.json`.
- Do not touch / revert root `settings.json`.
- Do not use destructive git commands.
- Do not mark the goal complete while known product blockers remain.
- Keep API / Gemini / remote LLM out of the product execution path.
- Do not use or download China-source models.
- Do local LLM disk / VRAM / cache preflight before any model download.
- Commit each verified slice locally.

## Resume Check

Start with:

```bash
git status --short
git log --oneline -n 10
sed -n '1,220p' artifacts/goal/handoff-2026-05-04-usage-refresh.md
tail -n 120 docs/records/worklog.md
tail -n 160 docs/records/implementation_log.md
```

Expected unrelated dirty files:

```text
 M .vscode/settings.json
 M settings.json
```

Do not stage or revert those files.

## Latest Completed Product Commits

```text
26bed60 validation: probe pyvistaqt runtime
ed4bec6 validation: capture launcher geometry
dd9a653 backend: apply mat sample anchors
94e77dd validation: add data interpretation format matrix
b5f2c29 docs: refresh usage handoff
3ffa73d mcp: verify inspector cli config
4e9cdfc ui: select label carrier targets
4f36615 ui: map generic label carriers manually
eb04399 mcp: add client release config
```

Recent evidence is recorded in:

- `artifacts/data_interpretation/format-capability-matrix.md`
- `artifacts/launcher/windows-launcher-walkthrough.md`
- `artifacts/ui/visualization-render/pyvistaqt-runtime-probe.md`
- `artifacts/mcp/inspector-cli-tools-list.md`
- `docs/current.md`
- `docs/planning/now.md`
- `docs/validation/README.md`
- `docs/records/worklog.md`
- `docs/records/implementation_log.md`

## Product State

- Data Interpretation has ApplicationService-backed
  `scan -> preview -> validate -> confirm/apply -> recipe` baseline.
- Import wizard supports metadata / class-map / label-carrier review, generic
  carrier target selection, and narrow MAT sample-index anchor apply.
- Full post-load label editing is still not a mature embedded Data
  Interpretation recipe UI; old compatibility flow must not become the main
  product mental model.
- MCP server and external-client config exist; official Inspector CLI
  `tools/list` works through Windows WSL config. Inspector GUI click-through is
  still open.
- Windows launcher automated command walkthrough and startup geometry diagnostics
  pass. Human Desktop click-through / multi-monitor verification is still open.
- Matplotlib saliency tabs render in MainWindow evidence. Headless/offscreen 3D
  is guarded. Interactive PyVistaQt is blocked in the current runner with X
  `BadWindow` and is still open.
- Local tool-call thesis-candidate benchmark evidence exists for `100` cases,
  primary / fallback x3. It does not by itself close product readiness.

## Recommended Next Slice

Highest-value next slice:

```text
Embedded Data Interpretation label editor
```

Target behavior:

- Primary UI path lets the user resolve label/event carrier target, event role,
  class map, anchor, and subject/session/task/run metadata inside the Data
  Interpretation recipe flow.
- Old `load_data` / `attach_labels` paths remain compatibility only.
- UI text is user-facing, not schema/debug wording.
- `ApplicationService` remains the only execution path for UI / agent /
  headless / MCP.
- Evidence includes UI-observable replay with visible text/button state plus
  low-mock backend tests.

Suggested starting files:

```text
XBrainLab/backend/application/data_interpretation.py
XBrainLab/backend/application/service.py
XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py
XBrainLab/ui/handlers/dataset_action_handler.py
scripts/dev/capture_data_interpretation_replay.py
tests/unit/backend/application/test_application_service.py
tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py
docs/target/data_interpretation_system.md
```

Use TDD where behavior is concrete:

1. Add failing backend test for the new recipe editor result contract.
2. Add failing UI test for visible selector / confirmation state.
3. Implement the smallest product-shaped editor changes.
4. Run targeted tests and replay.
5. Update docs/records.
6. Commit only that verified slice.

## Remaining Product Blockers

Goal must remain incomplete while these remain:

- Full embedded Data Interpretation label editor is incomplete.
- Raw-event-anchor-specific GDF / MAT alignment remains incomplete.
- XDF / LSL stream parser remains incomplete.
- Full real-data manual compatibility certification remains incomplete.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior is
  not manually verified.
- Interactive desktop 3D / PyVista render is not verified.
- MCP Inspector GUI click-through is not done.
- External thesis experiment runner / statistical report is not done.
- Final full validation sweep has not been rerun after all product slices.

## If Blocked Again

- Do not mark complete.
- Commit verified slices only.
- Update `docs/records/worklog.md`.
- Update `docs/records/implementation_log.md`.
- Refresh `artifacts/goal/handoff-2026-05-04-usage-refresh.md`.
- Refresh this continuation prompt.
