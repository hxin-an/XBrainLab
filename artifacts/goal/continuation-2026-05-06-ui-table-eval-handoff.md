# XBrainLab Product Completion Continuation - 2026-05-06 UI Table / Eval Gate

Use this as the next-run handoff for the active product-completion goal. Do not
mark Goal 1 product-complete while the blockers below remain.

## Current Repo / Branch

- Repo: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
- Branch: `codex/stabilization-autopilot`
- Do not push.
- Do not touch / stage / revert `.vscode/settings.json`, root `settings.json`, or the user-added
  `.agents/skills/*` changes unless the user explicitly asks.

Expected dirty files after this handoff:

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

## Latest Validated Commits

```text
1e3c1a7 test: record dataset table fill geometry
538256c ui: widen interpretation carrier columns
5106710 ui: polish interpretation review tables
fc6bc79 ui: route preprocess legacy shared refresh
```

## What Was Closed In This Slice

- Data Interpretation wizard selector visible text:
  - label carrier selectors show user-facing labels such as `Trial type` / `Onset`.
  - backend recipe choices still preserve raw values such as `trial_type`.
- Review Summary contrast:
  - alternate row color lowered to `#232323`, avoiding harsh black/white striping.
- Label/Event review table readability:
  - label-carrier `Format` column widened so `BIDS events` remains visible in product-width dialog.
- Dataset loaded table artifact:
  - `artifacts/ui/data-interpretation-applied.png` shows loaded rows filling to the sidebar.
  - `Labels (4)` is muted text, not success-green.
- Automated geometry guard:
  - `table_state()` now records `widget_width`, `panel_width`, `table_right_x`,
    `right_boundary_x`, and `right_gap_to_boundary`.
  - `build_table_geometry_review()` now fails if a table fills only its own viewport but leaves a
    visible gap before the content boundary.
  - Latest `artifacts/ui/data-interpretation-replay.json` records
    `widget_width=1020`, `table_right_x=1020`, `right_boundary_x=1020`,
    `right_gap_to_boundary=0` for the 1280px loaded Dataset capture.

## Validation Already Run

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_data_interpretation_replay.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_table_columns_fill_available_width \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_refits_table_after_loaded_rows_settle \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_events_column_uses_semantic_text_and_muted_color \
  -q
# 23 passed

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py
# exit 0

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
# exit 0; walkthrough status passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run mkdocs build --strict
poetry run python tests/architecture_compliance.py
# all passed; mkdocs still prints the existing Material advisory
```

No local LLM eval was run for this UI/layout slice.

## Tool-Call Eval Gate Policy

Do not run full primary/fallback x3 local eval for routine changes.

- Fast dev gate:
  - deterministic eval
  - changed / failed cases only
  - repeat `1`
  - no fallback model
- Candidate gate:
  - primary model only
  - affected case families
  - repeat `1` or `2`
- Release / thesis gate:
  - deterministic full suite
  - primary full suite x3
  - fallback full suite x3
  - dashboard refresh
  - record disk / cache / `nvidia-smi` VRAM used/free, latency, and resource pressure

RTX 5070 Ti 16GB has already shown near-full VRAM pressure on fallback x3. If VRAM is nearly full,
do not start a full fallback x3 run. Use deterministic changed cases or primary subset unless the
work is explicitly a release / thesis evidence gate.

## Still Cannot Claim Product Complete

- UI refresh remains partially mixed:
  - command-result coordinator baseline exists, but observer/manual/tab-switch/event-specific
    refreshes still remain.
- Product runtime controller fallback is still an audit target:
  - controller fallback must stay explicit mock / unit-test / legacy-only, not silent product
    runtime mutation.
- Data Interpretation is stronger but not final:
  - embedded label editor, raw trigger selector, complex GDF/MAT anchor reconciliation, XDF/LSL full
    parser, full real-data manual certification, and recipe diff/review UX remain.
- Human desktop acceptance remains open:
  - Windows launcher click-through, dual monitor / DPI, and long real local-model desktop session
    are not verified.
- Agent / MCP release depth remains open:
  - long autonomous ChatPanel workflow, UI-routing render, full recovery behavior, HTTP MCP
    transport, and long-running MCP job progress/cancel/recovery remain.
- Tool-call benchmark evidence must not be used as UI / launcher / import wizard product evidence.

## Suggested Next Slices

1. Continue `UI Command Refresh Coordinator + Controller Fallback Audit`.
   - Pick one remaining mutating UI path.
   - Add a focused test that service-success does not fall back to controller mutation in real
     `Study` context.
   - Route post-command refresh through the coordinator.
2. Continue Data Interpretation wizard maturity.
   - Add a small recipe diff/review UX slice or a safer label-carrier edit slice with screenshot
     artifact.
3. Only after product/UI/backend path stabilizes, refresh affected tool-call eval cases using the
   fast/candidate gate. Reserve full primary/fallback x3 for release/thesis evidence.
