# XBrainLab Session Log

This log records meaningful progress so repair work can continue smoothly across sessions.

## 2026-04-18

### Environment and takeover baseline

- prepared WSL2 development environment for the project
- installed Poetry and project dependencies
- installed headless GUI tooling for PyQt work
- verified app startup to `MainWindow`
- verified UI unit test baseline in WSL headless mode

### Takeover governance docs

- created:
  - `AGENTS.md`
  - `docs/TAKEOVER.md`
  - `docs/TESTING_STRATEGY.md`
  - `docs/UI_BASELINE.md`
  - `docs/WORKFLOWS.md`
  - `docs/BUG_TRIAGE.md`
  - `docs/RISK_CLUSTERS.md`
  - `docs/DIALOG_MATRIX.md`
  - `docs/COVERAGE_GAPS.md`
  - `docs/BACKLOG.md`

### Shared shell safety

- expanded `tests/unit/ui/test_main_window_sync.py`
- added smoke protection for:
  - active nav state synchronization
  - target-panel-only refresh behavior
  - safe navigation when a panel lacks `update_panel()`
- validated:
  - `tests/unit/ui/test_main_window_sync.py`
  - `tests/integration/ui/test_ui_refresh.py`

### Visual baseline work

- added `scripts/dev/capture_ui_baseline.py`
- created `artifacts/ui/`
- generated the first baseline artifact
- confirmed the current screenshot output is black and therefore not yet trustworthy

### Import and label reliability work

- improved `.mat` label loading to prefer label-like variables such as `classlabel` instead of blindly taking the first variable
- added coverage for multi-variable `.mat` files where the first variable is not the actual label array
- improved UI feedback when label import applies zero labels instead of failing silently
- added backend warning log for legacy label-count mismatch
- made `EventLoader` fail clearly when:
  - the loaded label sequence is empty
  - selected event filtering removes all EEG events
- tightened alignment-truncation warning logic so mismatches are logged more accurately
- removed a numeric-only assumption from `ImportLabelDialog` so string sequence labels can be reviewed and mapped instead of failing at `int(...)`
- updated `EventLoader` sequence mode so categorical/string labels are converted to stable integer event IDs while quoted numeric labels still preserve their original codes
- widened label import service typing so the repaired path is represented consistently end to end
- stopped keying imported label files by basename alone so same-named label files from different folders can coexist in the import dialog
- added full-path tooltips to label mapping surfaces so multi-folder imports remain inspectable without changing layout structure
- fixed `LabelMappingDialog` auto-sort to prefer normalized exact matches over brittle substring-first matching such as `sub01` vs `sub010`
- fixed `EventFilterDialog` so stale saved selections from another dataset do not silently uncheck every event in a new dataset
- blocked `EventFilterDialog` from accepting an empty keep-list, preventing silent zero-event synchronization attempts
- removed the `DatasetActionHandler.import_label()` assumption that the first label file represents the whole batch
- made mixed timestamp/sequence label batches fail clearly instead of being misclassified by the first file
- stopped batch mapping dialog cancellation from surfacing as a fake "No Labels Applied" warning
- refactored `BackendFacade.attach_labels()` to use shared label-import behavior instead of its own basename-only, numeric-only attach path
- added support for epoch-style `.fif` files by falling back from `read_raw_fif()` to `mne.read_epochs()`
- added support for `.fif.gz` in the raw-data loader factory by matching the longest registered suffix instead of only the last split extension
- changed event-filter smart suggestions to aggregate across all candidate raw files instead of trusting only the first file
- improved dataset mismatch diagnostics so channel/sfreq/type/duration errors now report both expected and actual values with filenames
- added focused coverage for:
  - string sequence labels in `ImportLabelDialog`
  - categorical string labels in `EventLoader`
  - quoted numeric string labels preserving original event codes
  - same-basename label files from different folders in `ImportLabelDialog`
  - ambiguous label auto-matching in `LabelMappingDialog`
  - stale and empty selections in `EventFilterDialog`
  - batch import mode analysis in `DatasetActionHandler`
  - facade attach-label delegation and full-path mapping
  - epoch fallback for `.fif` and support for `.fif.gz`
  - multi-file smart-filter suggestions in `DatasetActionHandler`
  - richer mismatch diagnostics in `RawDataLoader`

### Validation run results

- `tests/unit/backend/load_data/test_label_loader.py` and `test_label_loader_coverage.py`: pass
- `tests/unit/backend/services/test_label_import_service.py`: pass
- `tests/unit/backend/controller/test_dataset_ctrl.py` and `test_dataset_controller.py`: pass
- `tests/unit/ui/test_ui_misc.py`: pass
- `tests/unit/backend/load_data/test_event_loader.py` and `test_event_loader_strict.py`: pass
- `tests/unit/backend/load_data/test_label_import.py`: pass
- `tests/unit/ui/dataset/test_import_label.py`: pass

### Next recommended moves

1. inspect remaining raw-loader assumptions for other common compressed or sidecar-based formats
2. look for dataset import failures caused by channel-name consistency rather than channel-count consistency
3. begin local-only AI mode cleanup and remote API removal planning

## 2026-04-19

### Real-data baseline confirmation

- confirmed the repo already contains three checked-in real EEG fixtures:
  - `tests/data/A01T.gdf`
  - `tests/data/A02T.gdf`
  - `tests/data/A03T.gdf`
- confirmed the paired label fixtures under `tests/data/label/`
- verified the current real-data footprint stays modest at roughly 98 MB total for the three GDF files

### Training/runtime stabilization

- reproduced a non-load-data failure where `torch.cuda.is_available()` reported `True` on this host but actual training crashed because the installed PyTorch build cannot execute on the detected RTX 5070 Ti
- updated `TrainingOption` to probe the requested CUDA device and fall back to CPU with a warning when the device is present but unusable
- added unit coverage for the fallback path in `tests/unit/backend/training/test_option.py`
- verified directly on this machine that a GPU-requested `TrainingOption` now resolves to:
  - `use_cpu=True`
  - `gpu_idx=None`
  - `device=cpu`

### Real-data integration coverage repair

- fixed two integration tests that were looking under `tests/integration/data/` instead of the actual checked-in fixture directory `tests/data/`
- un-skipped real-data coverage in:
  - `tests/integration/pipeline/test_real_data_pipeline.py`
  - `tests/integration/io/test_io_integration.py`

### Validation run results

- `tests/unit/backend/training/test_option.py`: 42 passed
- `tests/integration/pipeline/test_pipeline_integration.py`
- `tests/integration/pipeline/test_real_data_pipeline.py`
- `tests/integration/io/test_io_integration.py`
  result: 5 passed
- `tests/integration/controller/test_preprocess_controller.py`
- `tests/integration/pipeline/test_all_real_tools.py`
  result: 15 passed

### Notable runtime signals

- real GDF workflows still emit repeated MNE warnings about duplicate channel names (`EEG`), which is now a good candidate for the next real-data investigation
- CUDA compatibility warnings still appear from PyTorch before fallback, but the training path no longer crashes because it degrades to CPU

### Next recommended moves

1. investigate whether the repeated duplicate-channel-name warnings create downstream issues in channel selection, montage, or saved diagnostics
2. widen real-data validation to include a label-attached dataset generation and training smoke on the checked-in fixtures
3. continue broader stabilization outside load-data by tackling local-only AI mode cleanup or the black screenshot baseline bug

### Multi-format real-data fixture expansion

- generated a compact cross-format fixture pack under `tests/data/multiformat/`
- derived all fixtures from a 15-second, 8-channel slice of the real `A01T.gdf` recording to keep storage growth low while still using real signal data
- added the following checked-in extensions:
  - `.fif`
  - `.fif.gz`
  - epoch-style `.fif`
  - `.edf`
  - `.bdf`
  - `.vhdr` with `.eeg` and `.vmrk`
  - `.set`
- documented the fixture origin and purpose in `tests/data/multiformat/README.md`
- kept the added footprint small at roughly 696 KB total for the new multi-format pack

### Multi-format validation results

- manually verified `load_raw_data()` can load:
  - `A01T.gdf`
  - `A01T-mini-real_raw.fif`
  - `A01T-mini-real_raw.fif.gz`
  - `A01T-mini-real.edf`
  - `A01T-mini-real.bdf`
  - `A01T-mini-real.vhdr`
  - `A01T-mini-real.set`
  - `A01T-mini-real-epo.fif`
- manually verified `BackendFacade.load_data()` succeeds on the same set of extensions
- expanded `tests/integration/io/test_io_integration.py` so the real-data integration slice now covers both:
  - direct loader validation across all compact real fixtures
  - facade-level dataset import across the same extension set

### Additional validation run results

- `tests/integration/io/test_io_integration.py`: 19 passed

### New runtime signals

- the real BCI Competition GDF fixtures still trigger duplicate channel-name warnings from MNE, which now has a dedicated triage entry as a likely next real-data issue to investigate

### Codex harness and local workspace baseline

- created and switched to the working branch `codex/stabilization-autopilot`
- created the thread heartbeat automation `xbrainlab-autopilot` on a 30-minute cadence so stabilization work can continue in this conversation while the user is away
- installed the Poetry environment for the current `/mnt/d/repos/XBrainLab` workspace so the local Codex thread can run the project directly from this checkout
- confirmed startup smoke in the current workspace with:
  - `timeout 25s xvfb-run -a /home/administrator/.local/bin/poetry run python run.py`
  - result: startup reaches `MainWindow initialized` and stays alive until timeout
- re-confirmed the visual baseline blocker:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - result: still exits with `Captured screenshot is nearly all black`
- confirmed that targeted validation slices can pass in the current workspace when run with `-s`:
  - `tests/unit/backend/training/test_option.py`: 42 passed
  - `tests/unit/ui/test_main_window_sync.py`: 8 passed
  - `tests/integration/io/test_io_integration.py`: 19 passed
- identified a new local validation blocker:
  - default `pytest` capture currently fails at teardown in the `/mnt/d` Codex workspace, while the same slices succeed with `-s`

### Next recommended moves

1. update the repo docs to reflect the new Codex harness, prep gate, branch policy, and local validation assumptions
2. fix the black screenshot baseline output so `artifacts/ui/` becomes trustworthy
3. triage or repair the default pytest capture teardown failure in the current workspace

### Visual baseline repair

- replaced the fragile `scrot`-based helper path with direct Qt main-window capture in `scripts/dev/capture_ui_baseline.py`
- added focused unit coverage for the black-image heuristic in `tests/unit/scripts/test_capture_ui_baseline.py`
- re-ran:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - result: `artifacts/ui/main-window-initial.png` is now a visible main-window artifact rather than an all-black frame
- ran a combined validation slice with:
  - `tests/unit/scripts/test_capture_ui_baseline.py`
  - `tests/unit/backend/training/test_option.py`
  - `tests/unit/ui/test_main_window_sync.py`
  - `tests/integration/io/test_io_integration.py`
  - result: `71 passed, 5 warnings`

### Five-panel capture and public fixture expansion

- updated the capture helper so it now writes:
  - `artifacts/ui/main-window-initial.png`
  - `artifacts/ui/panel-dataset.png`
  - `artifacts/ui/panel-preprocess.png`
  - `artifacts/ui/panel-training.png`
  - `artifacts/ui/panel-evaluation.png`
  - `artifacts/ui/panel-visualization.png`
- created `scripts/dev/fetch_public_eeg_fixtures.py` to download a small cross-source EEG fixture set into `tests/data/public/`
- documented the public fixtures in `tests/data/public/README.md`
- downloaded and validated three external fixtures locally:
  - PhysioNet `physionet-eegmmidb-S008R01.edf`
  - BBCI `bbci-competition-iii-O3VR.gdf`
  - SCCN `sccn-eeglab_data.set`
- expanded `tests/integration/io/test_io_integration.py` so the real-data IO slice also covers these public EDF/GDF/SET fixtures when present
- validation result:
  - `tests/integration/io/test_io_integration.py`
  - result: `25 passed, 7 warnings`

### User-followable reporting

- added `docs/STATUS_REPORT.md` as the concise user-facing progress snapshot
- updated the Codex harness docs so future work cycles and heartbeat runs maintain this report
- updated the heartbeat operating cadence from 30 minutes to 10 minutes
- reshaped `docs/STATUS_REPORT.md` so it now mirrors the agreed long-running plan section-by-section instead of acting like a flat note dump
- re-ran the latest relevant validation after the report restructure:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - result: all six baseline images were regenerated successfully
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/scripts/test_capture_ui_baseline.py tests/integration/io/test_io_integration.py -q`
  - result: `27 passed, 7 warnings`

### Agent stack clarification

- clarified that the explicit agent-side stack should live under `.agents/`, not only inside `docs/`
- added `.agents/stack.md` to record:
  - selected default skills
  - conditional-only skills
  - rule policy
  - the heartbeat reading order
- updated `AGENTS.md`, `docs/CODEX_SETUP.md`, and `docs/AUTOPILOT.md` so unattended work reads `.agents/stack.md` before continuing
- expanded the external setup basis to include:
  - OpenAI Codex docs
  - Anthropic Claude Code docs
  - GitHub agent-skill docs
  - the vendor-neutral `agentmd` repository

### Full human-versus-agent doc split

- moved the canonical agent runtime surface into:
  - `.agents/runbooks/setup.md`
  - `.agents/runbooks/autopilot.md`
  - `.agents/runbooks/active-queue.md`
- kept `docs/` as the human-facing surface and added `docs/PLAN.md`
- converted these root-level docs into compatibility stubs:
  - `docs/CODEX_SETUP.md`
  - `docs/AUTOPILOT.md`
  - `docs/ACTIVE_QUEUE.md`
- created repo-local skills for repeated workflows:
  - `.agents/skills/xbrainlab-prep-gate/SKILL.md`
  - `.agents/skills/xbrainlab-repair-loop/SKILL.md`
- updated the canonical reading order so unattended work reads `.agents/` first, then the human-facing plan and progress docs

### Skill stack expansion

- reviewed official and high-signal skill ecosystems more deeply:
  - OpenAI Codex docs for skills and Docs MCP
  - Anthropic docs for focused subagents and project-scoped versioned assets
  - `anthropics/skills`
  - Awesome GitHub Copilot's public skills directory
- added narrower repo-local skills so the skill layer is not just `prep` and `repair`:
  - `.agents/skills/xbrainlab-workflow-baseline/SKILL.md`
  - `.agents/skills/xbrainlab-dialog-audit/SKILL.md`
  - `.agents/skills/xbrainlab-real-data-validation/SKILL.md`
  - `.agents/skills/xbrainlab-refresh-smoke/SKILL.md`
- added `agents/openai.yaml` metadata to the repo-local skills for a more complete local skill surface
- documented the selection rationale and reviewed-but-not-chosen ecosystem skills in `docs/AGENT_SKILLS.md`

### Updated next recommended moves

1. verify top-level panel happy paths and collect additional baseline artifacts beyond the initial shell
2. triage or repair the default pytest capture teardown failure in the current workspace
3. continue prep-gate work on high-risk dialog acceptance flows and downstream refresh propagation
