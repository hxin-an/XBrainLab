# XBrainLab Usage Refresh Handoff

Date: `2026-05-04`, after local commit `3ffa73d`.

This handoff exists because the current runner is stopping for usage refresh.
Resume in the active repo:

```text
/mnt/d/workspace_v2/projects/lab/XBrainLab
```

## Hard Boundaries

- Do not push.
- Do not touch or revert `.vscode/settings.json`.
- Do not touch or revert root `settings.json`.
- Do not run destructive git commands.
- Do not mark the product goal complete while known blockers remain.
- Keep API / Gemini / remote LLM out of the product execution path.
- Do not use or download China-source models.
- Do disk / VRAM / cache preflight before any model download.
- Keep local model cache within the existing limits unless the user explicitly approves otherwise.
- Commit each verified slice locally.

## Worktree Snapshot

Latest local commits at handoff:

```text
3ffa73d mcp: verify inspector cli config
4e9cdfc ui: select label carrier targets
4f36615 ui: map generic label carriers manually
eb04399 mcp: add client release config
0bdfdf8 docs: refresh usage handoff
15002a1 ui: show label import target context
7d0f92c ui: show matched eeg for label carriers
4c2ad99 backend: map reviewed sequence labels by file stem
c9c79e2 backend: map reviewed timestamp labels by file stem
a26942a backend: propagate import review state
514587a docs: refresh product completion handoff
0da24db backend: apply reviewed sequence labels during import
```

Expected dirty files before the next work slice:

```text
 M .vscode/settings.json
 M settings.json
```

These two files are protected user / workspace settings. Ignore them unless the
user explicitly asks otherwise. Do not stage them in any product or handoff
commit.

## Completed Slices Since The Previous Handoff

### MCP client release config

Committed as:

```text
eb04399 mcp: add client release config
```

Files of interest:

- `scripts/dev/run_mcp_server_for_client.sh`
- `scripts/dev/write_mcp_client_config.py`
- `artifacts/mcp/xbrainlab-mcp.json`
- `artifacts/mcp/xbrainlab-mcp.md`
- `tests/unit/scripts/test_write_mcp_client_config.py`
- `tests/integration/mcp/test_client_config.py`

Outcome:

- Added standard MCP client config with `default-server` and `xbrainlab-windows-wsl`.
- Client config launches a prepared XBrainLab runtime through a wrapper; MCP clients do not need EEG / PyQt / PyTorch dependencies.
- Config writer regenerates JSON / Markdown and validates the dependency boundary.

Validation:

- `poetry run pytest --capture=sys tests/unit/scripts/test_write_mcp_client_config.py -q` -> `5 passed`
- `poetry run pytest --capture=sys tests/unit/scripts/test_write_mcp_client_config.py tests/integration/mcp/test_client_config.py -q` -> `6 passed`
- `poetry run pytest --capture=sys tests/unit/scripts/test_write_mcp_client_config.py tests/unit/mcp tests/integration/mcp -q` -> `13 passed`
- targeted `ruff`, format, `basedpyright`, architecture compliance, MkDocs strict, and diff check passed.

### Generic label carrier manual target mapping

Committed as:

```text
4f36615 ui: map generic label carriers manually
```

Files of interest:

- `XBrainLab/backend/application/data_interpretation.py`
- `XBrainLab/backend/application/service.py`
- `XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py`
- `scripts/dev/capture_data_interpretation_replay.py`
- `tests/unit/backend/application/test_application_service.py`
- `tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
- `artifacts/ui/data-interpretation-preview.png`
- `artifacts/ui/data-interpretation-applied.png`
- `artifacts/ui/data-interpretation-replay.json`

Outcome:

- `label_carrier_choices` now accepts `target_file`.
- Backend persists `selected_target_file` in `label_carrier_plan`.
- `apply_interpretation` can apply generic `events.tsv` or `labels.mat` to the user-selected loaded EEG file.
- If no manual target is selected, ambiguous generic multi-file carriers still skip instead of guessing.

Validation:

- Initial TDD failures proved the missing UI result and backend apply behavior.
- Dialog suite -> `7 passed`
- Focused backend manual mapping and ambiguous skip tests -> `4 passed`
- Backend / automation / agent surface regression -> `67 passed`
- Dialog + DatasetActionHandler regression -> `54 passed`
- True UI replay exited `0` and refreshed the replay artifacts.
- targeted `ruff`, format, `basedpyright`, architecture compliance, MkDocs strict, and diff check passed.

### Label target selector UX

Committed as:

```text
4e9cdfc ui: select label carrier targets
```

Files of interest:

- `XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py`
- `scripts/dev/capture_data_interpretation_replay.py`
- `tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
- `artifacts/ui/data-interpretation-preview.png`

Outcome:

- Ambiguous label carrier rows now render a `QComboBox` in the `Matched EEG` column.
- Options are `Needs review` plus scanned EEG filenames.
- `get_result()` reads selector current text and returns `target_file`.
- Replay extraction reads cell widget text, so the visible selected target appears in artifacts.

Validation:

- Initial focused UI test failed because the row had no cell widget.
- Focused selector test -> `1 passed`
- Dialog suite -> `7 passed`
- True UI replay exited `0`
- Dialog + DatasetActionHandler regression -> `54 passed`
- Backend manual target mapping focused tests -> `2 passed`
- targeted `ruff`, format, and production `basedpyright` passed.

### MCP Inspector CLI smoke and WSL Poetry fallback

Committed as:

```text
3ffa73d mcp: verify inspector cli config
```

Files of interest:

- `scripts/dev/run_mcp_server_for_client.sh`
- `artifacts/mcp/inspector-cli-tools-list.json`
- `artifacts/mcp/inspector-cli-tools-list.md`
- `artifacts/mcp/xbrainlab-mcp.md`

Outcome:

- First official Inspector CLI attempt using `xbrainlab-windows-wsl` failed with:
  `Failed to connect to MCP server: MCP error -32000: Connection closed`.
- Direct WSL smoke found root cause: `exec: poetry: not found`.
- Wrapper now resolves `POETRY_BIN`, `command -v poetry`, or `$HOME/.local/bin/poetry`.
- Official Inspector CLI `tools/list` now succeeds through the committed Windows WSL config.
- Artifact lists `28` tools, including `scan_source` and `apply_interpretation`.

Validation:

- Direct WSL initialize smoke -> valid JSON-RPC initialize response.
- Official Inspector CLI:

  ```bash
  timeout 180s '/mnt/c/Program Files/nodejs/npx' -y @modelcontextprotocol/inspector --cli --config artifacts/mcp/xbrainlab-mcp.json --server xbrainlab-windows-wsl --method tools/list
  ```

  exited `0`.
- `poetry run pytest --capture=sys tests/unit/scripts/test_write_mcp_client_config.py tests/integration/mcp/test_client_config.py -q` -> `6 passed`
- `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
- `git diff --check` -> pass.

## Current Evidence Highlights

- Data Interpretation has ApplicationService-backed scan -> preview -> validate -> confirm/apply -> recipe baseline.
- Import wizard can review metadata, class map, and label carriers.
- Single-file and safe multi-file reviewed timestamp / trial-order label apply paths are covered.
- Generic label carriers can now be manually mapped to a specific EEG target inside the wizard.
- Format-specific supported / needs-review / blocked boundaries exist in code for GDF, EDF / BDF, EEGLAB, BrainVision, MNE FIF, MAT labels, CSV / TSV / BIDS events, TXT, and blocked XDF / LSL stream-selection cases.
- Shared import truth propagates into UI / agent / headless / MCP state.
- True local ChatPanel controlled tiny training completion evidence exists under `artifacts/ui/chatpanel-local-training-completion/`.
- Visualization render evidence exists under `artifacts/ui/visualization-render/`; Saliency Map, Spectrogram, and Topographic Map render in a true MainWindow walkthrough after a tiny CPU training run.
- Headless/offscreen `3D Plot` is guarded and shows a human-readable blocked reason instead of creating a PyVista plotter and crashing.
- MCP server can be launched by an external client config and official Inspector CLI can list tools through the Windows WSL config.
- Local tool-call thesis-candidate benchmark evidence exists for `100` cases, primary / fallback x3, with cached non-China local models and no download.

## Do Not Redo Without Reason

- Do not redo true ChatPanel training-completion walkthrough unless local model agent execution, training command surface, evaluation, saliency, or visible ChatPanel feedback changed.
- Do not redo visualization render walkthrough unless visualization panel, training state, saliency, or render contract changed.
- Do not redo label carrier wizard review / format boundary / label apply work unless `data_interpretation.py`, wizard result mapping, scan format detection, recipe serialization, or state snapshot propagation changed.
- Do not redo full local LLM x3 eval for documentation-only edits. Rerun targeted eval if prompt / schema / parser / verifier behavior changes, then rerun full primary / fallback x3 before thesis-candidate claims.
- Do not redo MCP client config generation or Inspector CLI `tools/list` unless `artifacts/mcp/xbrainlab-mcp.json`, the wrapper, or MCP server transport/schema changes.

## Current Known Blockers

Do not claim product completion yet.

- Inspector GUI human click-through is still not done. CLI smoke is done.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior has not been manually verified.
- Interactive desktop 3D / PyVista render has not been verified; only headless blocked UX and Matplotlib tabs are proven.
- Raw-event-anchor-specific GDF / MAT alignment is not modeled.
- Full all-format manual compatibility matrix and XDF / LSL stream parser remain incomplete.
- Post-load label import is improved, but still not a full embedded Data Interpretation label editor.
- External thesis experiment runner / statistical report is not done.
- Thesis-candidate local LLM evidence exists, but the full product claim still depends on UI, launcher, MCP GUI, import, and experiment validation.

## Immediate Resume Plan

1. Re-check worktree:

   ```bash
   git status --short
   ```

   Only `.vscode/settings.json` and root `settings.json` should be unrelated protected dirty files after this handoff commit.

2. Recommended next product slice:

   ```text
   Data Interpretation format capability matrix
     -> generate a checked-in artifact from actual scan/preview code, not docs-only claims
     -> cover representative source files for GDF, EDF/BDF, EEGLAB, BrainVision, FIF,
        MAT labels, CSV/TSV/BIDS events, TXT labels, and XDF/LSL
     -> assert supported / needs-review / blocked statuses and user-facing reasons
     -> document that this is current capability-boundary evidence, not a full XDF parser
     -> update docs/records
     -> local commit
   ```

   Suggested files / functions to inspect:

   ```text
   XBrainLab/backend/application/data_interpretation.py
   scripts/dev/report_dataset_validation_matrix.py
   tests/unit/scripts/
   docs/validation/README.md
   ```

3. After the matrix slice, continue with remaining product blockers:

   - embedded post-load label import editor hardening;
   - raw-event-anchor-specific GDF / MAT alignment design and implementation;
   - Windows Desktop launcher human click-through / WSLg multi-monitor verification;
   - Inspector GUI click-through;
   - interactive desktop 3D render verification if a real OpenGL desktop session is available;
   - external thesis experiment runner / statistical report;
   - final validation sweep and docs closure.

## Claim Boundary

Current evidence supports:

- ApplicationService-backed Data Interpretation baseline;
- import wizard metadata / class-map / label carrier review;
- single-file, safe multi-file, and manually mapped generic timestamp / trial-order label apply;
- shared import truth propagation to UI / agent / headless / MCP state;
- official Inspector CLI `tools/list` through committed Windows WSL client config;
- true local ChatPanel single-command-per-turn workflow through controlled tiny training completion;
- true MainWindow post-training Matplotlib visualization render evidence;
- headless 3D blocked UX.

Current evidence does not support:

- completed desktop product;
- completed mature embedded import wizard label editor;
- completed raw-event-anchor label alignment;
- completed Windows Desktop human click-through;
- completed Inspector GUI click-through;
- completed interactive desktop 3D render;
- completed external thesis experiment package;
- full product thesis-ready claim.

Goal status must remain incomplete.
