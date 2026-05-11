# XBrainLab Usage Refresh Handoff

Snapshot date: `2026-05-04`

Product evidence snapshot: after local product commit
`26bed60 validation: probe pyvistaqt runtime`. The handoff / continuation docs
are committed after that product snapshot.

This handoff exists because the current runner is pausing for usage refresh.
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

Latest product commits captured by this handoff:

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
0bdfdf8 docs: refresh usage handoff
```

Expected dirty files after this handoff commit:

```text
 M .vscode/settings.json
 M settings.json
```

These two files are protected user / workspace settings. Ignore them unless the
user explicitly asks otherwise. Do not stage them in any product or handoff
commit.

## Completed Slices Since The Previous Handoff

### Data Interpretation format capability matrix

Committed as:

```text
94e77dd validation: add data interpretation format matrix
```

Files of interest:

- `scripts/dev/report_data_interpretation_format_matrix.py`
- `tests/unit/scripts/test_report_data_interpretation_format_matrix.py`
- `artifacts/data_interpretation/format-capability-matrix.json`
- `artifacts/data_interpretation/format-capability-matrix.md`
- `docs/current.md`
- `docs/planning/now.md`
- `docs/validation/README.md`
- `docs/records/worklog.md`
- `docs/records/implementation_log.md`

Outcome:

- Added a generated capability-boundary matrix from live `ApplicationService`
  `scan_source -> preview_interpretation -> validate_interpretation`.
- Covers GDF, EDF, BDF, EEGLAB SET, BrainVision VHDR / VMRK, MNE FIF, MAT labels,
  CSV labels, TSV labels, BIDS `events.tsv`, TXT labels, and blocked XDF / LSL
  stream export.
- Rows include current support status and validation decision, without claiming
  unsupported formats are usable.

Validation:

- `poetry run pytest --capture=sys tests/unit/scripts/test_report_data_interpretation_format_matrix.py -q` -> `3 passed`
- `poetry run pytest --capture=sys tests/unit/scripts/test_report_data_interpretation_format_matrix.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries -q` -> `4 passed`
- targeted `ruff check` / `ruff format --check` -> pass
- `poetry run basedpyright scripts/dev/report_data_interpretation_format_matrix.py` -> clean
- `poetry run python scripts/dev/report_data_interpretation_format_matrix.py --write-artifacts` -> wrote artifacts
- `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning
- `poetry run python tests/architecture_compliance.py` -> Architecture compliant
- `git diff --check` -> pass

Claim boundary:

- Supports generated capability-boundary evidence.
- Does not support XDF / LSL parser completion, raw-event-anchor-specific
  MAT/GDF alignment, real-data manual certification, or product completion.

### Reviewed MAT sample-anchor apply

Committed as:

```text
dd9a653 backend: apply mat sample anchors
```

Files of interest:

- `XBrainLab/backend/load_data/label_loader.py`
- `XBrainLab/backend/application/service.py`
- `tests/unit/backend/load_data/test_label_loader_coverage.py`
- `tests/unit/backend/application/test_application_service.py`
- `docs/current.md`
- `docs/planning/now.md`
- `docs/validation/README.md`
- `docs/records/worklog.md`
- `docs/records/implementation_log.md`

Outcome:

- `load_label_file(..., label_field="classlabel", anchor="cue_onset")` for MAT
  now resolves both variables and returns MNE-style event rows
  `[sample_index, 0, class_label]`.
- Reviewed MAT label carrier plans can apply when they include selected label,
  selected anchor, `time_model=sample_index`, `granularity=trial`, and class map.
- `apply_interpretation` records `label_import:anchored:<n>` in the recipe trace.

Validation:

- focused MAT anchor tests -> `2 passed`
- label loader + label apply regression subset -> `35 passed`
- full `tests/unit/backend/application/test_application_service.py` -> `43 passed`
- targeted `ruff check` / `ruff format --check` -> pass
- `poetry run basedpyright XBrainLab/backend/load_data/label_loader.py XBrainLab/backend/application/service.py` -> clean
- `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning
- `poetry run python tests/architecture_compliance.py` -> Architecture compliant
- `git diff --check` -> pass

Claim boundary:

- Supports the narrow reviewed MAT sample-index anchor apply path.
- Does not support arbitrary raw trigger selection, non-sample timestamp
  conversion, complex MAT/GDF anchor reconciliation, XDF parser, or real-data
  manual certification.

### Windows launcher geometry capture

Committed as:

```text
ed4bec6 validation: capture launcher geometry
```

Files of interest:

- `scripts/dev/capture_windows_launcher_walkthrough.py`
- `scripts/launchers/xbrainlab_wsl_launcher.ps1`
- `tests/unit/scripts/test_capture_windows_launcher_walkthrough.py`
- `artifacts/launcher/windows-launcher-walkthrough.json`
- `artifacts/launcher/windows-launcher-walkthrough.md`
- `docs/current.md`
- `docs/planning/now.md`
- `docs/validation/README.md`
- `docs/records/worklog.md`
- `docs/records/implementation_log.md`

Outcome:

- Launcher smoke now forces `XBRAINLAB_STARTUP_DIAGNOSTICS=1`.
- Capture verifies screen count/detail, splash geometry, main-window geometry,
  active repo resolution, WSL stdout/stderr mirroring, MainWindow initialization,
  and bounded timeout.
- Latest artifact points at Windows log
  `/mnt/c/Users/Administrator/AppData/Local/XBrainLab/logs/launcher-20260504-193942.log`
  and has status `passed`.

Validation:

- `timeout 180s poetry run python scripts/dev/capture_windows_launcher_walkthrough.py --output-dir artifacts/launcher --startup-timeout 150` -> passed and wrote artifacts
- `poetry run pytest --capture=sys tests/unit/scripts/test_capture_windows_launcher_walkthrough.py -q` -> `3 passed`
- targeted `ruff check` / `ruff format --check` -> pass
- `poetry run basedpyright scripts/dev/capture_windows_launcher_walkthrough.py` -> clean
- `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning
- `poetry run python tests/architecture_compliance.py` -> Architecture compliant
- `git diff --check` -> pass

Claim boundary:

- Supports automated Windows launcher command path and startup geometry
  diagnostics.
- Does not replace human Desktop click-through, packaged release approval, or
  real multi-monitor interaction.

### PyVistaQt runtime probe

Committed as:

```text
26bed60 validation: probe pyvistaqt runtime
```

Files of interest:

- `scripts/dev/probe_pyvistaqt_runtime.py`
- `tests/unit/scripts/test_probe_pyvistaqt_runtime.py`
- `artifacts/ui/visualization-render/pyvistaqt-runtime-probe.json`
- `artifacts/ui/visualization-render/pyvistaqt-runtime-probe.md`
- `docs/current.md`
- `docs/planning/now.md`
- `docs/validation/README.md`
- `docs/records/worklog.md`
- `docs/records/implementation_log.md`

Outcome:

- Added a child-process PyVistaQt probe that records stable JSON / Markdown
  evidence instead of losing X errors in the terminal.
- In the current runner session, minimal `pyvistaqt.QtInteractor` + sphere render
  is blocked with X `BadWindow (invalid Window parameter)`.
- The artifact captures `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`, no screenshot,
  and status `blocked`.

Validation:

- exploratory direct probe failed with X `BadWindow`
- `timeout 90s poetry run python scripts/dev/probe_pyvistaqt_runtime.py --output-dir artifacts/ui/visualization-render --timeout-seconds 60` -> wrote blocked artifacts
- `poetry run pytest --capture=sys tests/unit/scripts/test_probe_pyvistaqt_runtime.py -q` -> `2 passed`
- targeted `ruff check` / `ruff format --check` -> pass
- `poetry run basedpyright scripts/dev/probe_pyvistaqt_runtime.py` -> clean
- `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning
- `poetry run python tests/architecture_compliance.py` -> Architecture compliant
- `git diff --check` -> pass

Claim boundary:

- Supports that the current runner session cannot verify interactive PyVistaQt.
- Does not support XBrainLab 3D saliency render, human OpenGL desktop
  walkthrough, or product completion.

## Current Evidence Highlights

- Data Interpretation has ApplicationService-backed
  `scan -> preview -> validate -> confirm/apply -> recipe` baseline.
- Import wizard can review metadata, class map, and label carriers.
- Generic label carriers can be manually mapped to a specific scanned EEG target
  inside the wizard.
- Single-file and safe multi-file reviewed timestamp / trial-order label apply
  paths are covered.
- Reviewed MAT sample-index anchor labels can apply through the narrow confirmed
  plan path.
- Generated format capability matrix records supported / needs-review / blocked
  boundaries for the representative import formats.
- Shared import truth propagates into UI / agent / headless / MCP state.
- True local ChatPanel controlled tiny training completion evidence exists under
  `artifacts/ui/chatpanel-local-training-completion/`.
- Visualization render evidence exists under
  `artifacts/ui/visualization-render/`; Saliency Map, Spectrogram, and
  Topographic Map render in a true MainWindow walkthrough after a tiny CPU
  training run.
- Headless/offscreen `3D Plot` is guarded and shows a human-readable blocked
  reason instead of creating a PyVista plotter and crashing.
- PyVistaQt runtime probe is blocked in the current runner session with X
  `BadWindow`; this keeps the interactive 3D claim open instead of hiding it.
- MCP server can be launched by an external client config, and official Inspector
  CLI can list tools through the Windows WSL config.
- Local tool-call thesis-candidate benchmark evidence exists for `100` cases,
  primary / fallback x3, with cached non-China local models and no download.

## Do Not Redo Without Reason

- Do not redo true ChatPanel training-completion walkthrough unless local model
  agent execution, training command surface, evaluation, saliency, or visible
  ChatPanel feedback changed.
- Do not redo visualization render walkthrough unless visualization panel,
  training state, saliency, or render contract changed.
- Do not redo Data Interpretation label carrier wizard review / format boundary
  / label apply work unless `data_interpretation.py`, wizard result mapping, scan
  format detection, recipe serialization, or state snapshot propagation changed.
- Do not redo full local LLM x3 eval for documentation-only edits. Rerun
  targeted eval if prompt / schema / parser / verifier behavior changes, then
  rerun full primary / fallback x3 before thesis-candidate claims.
- Do not redo MCP client config generation or Inspector CLI `tools/list` unless
  `artifacts/mcp/xbrainlab-mcp.json`, the wrapper, or MCP server
  transport/schema changes.

## Current Known Blockers

Do not claim product completion yet.

- Inspector GUI human click-through is still not done. CLI smoke is done.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior has
  not been manually verified.
- Interactive desktop 3D / PyVista render is blocked in the current runner
  session and has not been verified as product UI.
- Raw-event-anchor-specific GDF / MAT alignment is not modeled.
- XDF / LSL stream parser remains incomplete.
- Full real-data manual compatibility certification remains incomplete.
- Post-load label import is improved, but still not a full embedded Data
  Interpretation label editor.
- External thesis experiment runner / statistical report is not done.
- Thesis-candidate local LLM evidence exists, but the full product claim still
  depends on UI, launcher, MCP GUI, import, and experiment validation.

## Immediate Resume Plan

1. Re-check worktree:

   ```bash
   git status --short
   git log --oneline -n 10
   ```

   Only `.vscode/settings.json` and root `settings.json` should be unrelated
   protected dirty files after this handoff commit.

2. Recommended next product slice:

   ```text
   Embedded Data Interpretation label editor
     -> replace remaining legacy "Add Labels to Loaded Data" mental model in
        primary UI paths
     -> let users resolve carrier target, event role, class map, anchor, and
        subject/session/task/run metadata from the recipe UI
     -> keep old load_data / attach_labels as compatibility only
     -> add visible UI replay and low-mock ApplicationService tests
     -> update docs/records and local commit
   ```

3. Other high-value slices if the label editor is blocked by runtime limits:

   ```text
   MCP Inspector GUI click-through artifact
   Windows Desktop human click-through / multi-monitor artifact
   XDF / LSL boundary or parser decision with tests
   external thesis experiment runner / statistical report
   ```
