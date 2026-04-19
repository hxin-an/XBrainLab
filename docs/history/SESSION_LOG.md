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
  - `docs/workflows/TAKEOVER.md`
  - `docs/workflows/TESTING_STRATEGY.md`
  - `docs/workflows/UI_BASELINE.md`
  - `docs/workflows/WORKFLOWS.md`
  - `docs/current/BUG_TRIAGE.md`
  - `docs/workflows/RISK_CLUSTERS.md`
  - `docs/workflows/DIALOG_MATRIX.md`
  - `docs/workflows/COVERAGE_GAPS.md`
  - `docs/history/BACKLOG.md`

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

- added `docs/current/STATUS_REPORT.md` as the concise user-facing progress snapshot
- updated the Codex harness docs so future work cycles and heartbeat runs maintain this report
- updated the heartbeat operating cadence from 30 minutes to 10 minutes
- reshaped `docs/current/STATUS_REPORT.md` so it now mirrors the agreed long-running plan section-by-section instead of acting like a flat note dump
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
- updated `AGENTS.md`, `.agents/runbooks/setup.md`, and `.agents/runbooks/autopilot.md` so unattended work reads `.agents/stack.md` before continuing
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
- kept `docs/` as the human-facing surface and added `docs/current/PLAN.md`
- converted these root-level docs into compatibility stubs:
  - `.agents/runbooks/setup.md`
  - `.agents/runbooks/autopilot.md`
  - `.agents/runbooks/active-queue.md`
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
- documented the selection rationale and reviewed-but-not-chosen ecosystem skills in `docs/reference/AGENT_SKILLS.md`

### Human doc cleanup

- removed the compatibility-stub approach for human docs so `docs/` can stay cleaner
- moved the main user-facing status docs into:
  - `docs/current/PLAN.md`
  - `docs/current/STATUS_REPORT.md`
  - `docs/current/BUG_TRIAGE.md`
- moved workflow-heavy support docs into `docs/workflows/`
- moved long-running records into `docs/history/`
- moved skill-selection background into `docs/reference/AGENT_SKILLS.md`
- rewrote `docs/index.md` into a human-first docs portal that tells the user which three files to read first
- updated agent-side references and the `XBrainLab Autopilot` heartbeat prompt so unattended work follows the new doc layout instead of the removed root-level doc paths

### Top-level panel baseline and AI shell signal

- extended `scripts/dev/capture_ui_baseline.py` so the helper also captures `artifacts/ui/ai-assistant-open.png`
- added targeted unit coverage for the new capture-step behavior in `tests/unit/scripts/test_capture_ui_baseline.py`
- refreshed the headless baseline artifacts with:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - result: shell, five primary panels, and AI assistant open state were all captured successfully
- re-ran targeted validation for the helper:
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/scripts/test_capture_ui_baseline.py -q`
  - result: `4 passed`
- re-ran the Qt integration slice for shell-level workflow evidence:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q`
  - result: `20 passed`
- the same integration slice also exposed a confirmed AI assistant runtime issue:
  - first-open local model initialization fails with a missing-`accelerate` error in the current environment
- recorded that runtime signal as `BUG-AGENT-001`
- recorded a new durable design-boundary exception:
  - the user explicitly approved intentional redesign of the AI assistant panel

### Priority dialog acceptance coverage

- added `tests/integration/ui/test_dialog_acceptance.py` to exercise the four prep-gate priority dialogs through real widget interaction and the OK-button path:
  - `LabelMappingDialog`
  - `EventFilterDialog`
  - `EpochingDialog`
  - `TrainingSettingDialog`
- validation run:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_dialog_acceptance.py -q`
  - result: `4 passed`
- this narrows the modal blind spot significantly for the prep gate:
  - these dialogs are no longer covered only by direct method calls or patched dialog-entry mocks
  - the remaining caveat is that the broader test harness still patches `QDialog.exec`, so this is strong headless acceptance coverage rather than full manual desktop validation

### Shared refresh propagation coverage

- added `tests/unit/ui/test_panel_event_bridges.py` to exercise the highest-value observer-bridge propagation paths directly:
  - dataset events -> `PreprocessPanel.update_panel()`
  - dataset events -> `TrainingPanel.update_panel()`
  - `training_stopped` -> `EvaluationPanel.update_panel()`
  - `training_stopped` -> `VisualizationPanel.update_panel()`
- validation run:
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/ui/test_panel_event_bridges.py -q`
  - result: `4 passed`
- this complements the existing `MainWindow.switch_page()` smoke tests by checking the event-driven path instead of only tab navigation

### AI shell triage refinement

- confirmed that `accelerate` is already declared in `pyproject.toml`, but only under the optional Poetry `llm` group
- this narrows `BUG-AGENT-001`:
  - the current failure is not just "missing dependency in source control"
  - it is more specifically an environment/readiness mismatch plus missing UI-side preflight behavior before local backend startup

### Pytest capture triage refinement

- reproduced `BUG-ENV-003` again with:
  - `/home/administrator/.local/bin/poetry run pytest tests/unit/backend/training/test_option.py -q`
  - result: teardown failure in `_pytest/capture.py` after `no tests ran`
- split the failure by capture backend:
  - `--capture=fd` still fails
  - `--capture=sys` passes
  - `--capture=tee-sys` passes
  - `-s` also passes
- verified the `--capture=sys` workaround on representative slices:
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/training/test_option.py -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/ui/test_main_window_sync.py -q`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/ui/test_dialog_acceptance.py -q`
- conclusion:
  - the current workspace issue is specifically an `fd` capture problem, not a general pytest collection or execution failure
  - `--capture=sys` is now the preferred local workaround because it preserves capture behavior without the teardown crash

### AI assistant local-startup hardening

- refined `BUG-AGENT-001` from a single missing-`accelerate` symptom into two distinct problems:
  - the first-start worker path was ignoring persisted settings and constructing a fresh default `LLMConfig()`
  - the local backend path was discovering missing runtime packages too late, after startup had already entered backend initialization
- updated `AgentWorker.initialize_agent()` so first initialization now loads persisted settings before selecting a backend
- added local-runtime readiness helpers to `LLMConfig` and used them in:
  - `AgentWorker`
  - `ChatPanel.update_model_menu()`
  - `ModelSettingsDialog`
- changed the current assistant direction to local-only startup rather than solving bootstrap failures through Gemini fallback
- validated the hardening patch with:
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py -q`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/dialogs/test_model_settings.py -q`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/ui/test_e2e_qtbot.py -q`
- remaining local-only blockers in this workspace:
  - no local model cache is present
  - the end-to-end local startup path still needs a clean run against a real downloaded model

### Local-only environment refinement

- installed the optional local-LLM dependencies in the current Poetry environment with:
  - `/home/administrator/.local/bin/poetry install --with llm --no-interaction`
- verified afterward that `LLMConfig.missing_local_runtime_packages()` now returns `[]`
- confirmed the next local-only blocker is not missing packages but host CUDA mismatch:
  - `torch.cuda.is_available()` still returns `True`
  - a direct CUDA allocation probe fails with `RuntimeError: CUDA error: no kernel image is available for execution on the device`
- updated `LocalBackend` so it now probes the configured CUDA device before model load and falls back to CPU while disabling 4-bit loading if the GPU is unusable
- validated the CUDA-fallback hardening with:
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py -q`
  - result: `50 passed`
- confirmed the expected cache directory for the configured local model still does not exist:
  - `/mnt/d/repos/XBrainLab/XBrainLab/llm/core/models/Qwen_Qwen2.5-7B-Instruct`
- attempted a standalone rerun of `tests/integration/ui/test_e2e_qtbot.py` after the environment change, but interrupted it after a hang past the AI-dock block, so that rerun is not being treated as accepted evidence in this cycle

### Updated next recommended moves

1. verify top-level panel happy paths and collect additional baseline artifacts beyond the initial shell
2. triage or repair the default pytest capture teardown failure in the current workspace
3. continue prep-gate work on high-risk dialog acceptance flows and downstream refresh propagation

### Thesis-direction doc consolidation

- clarified in `AGENTS.md` that this repository is the implementation workspace for the user's master's thesis
- recorded the current thesis order of work as:
  - stabilization first
  - tool-call agent redesign second
  - rigorous validation throughout
- simplified `docs/index.md` so the human entry point now emphasizes only the current status, plan, triage, and decision-record docs
- added `docs/decisions/README.md` as the decision-record entry point
- added `docs/decisions/ADR-011-thesis-direction.md` so future tool-call agent redesign work has one active design anchor instead of scattered notes
- updated `docs/current/PLAN.md` and `docs/current/STATUS_REPORT.md` so they now reflect the thesis framing rather than only the stabilization loop

### Repository-structure audit and redesign proposal

- completed a repository-wide structure audit across:
  - top-level folders
  - `docs/`
  - `XBrainLab/`
  - `tests/`
  - `scripts/`
  - root-level entry files such as `ROADMAP.md`, `CHANGELOG.md`, and `mkdocs.yml`
- identified the main structure problem as information sprawl rather than any single bad folder:
  - active docs
  - historical notes
  - API/reference material
  - thesis decisions
  - published-doc navigation
  were all competing at similar visibility
- added `docs/decisions/ADR-012-project-structure-redesign.md` as the proposed target repository and documentation information architecture
- updated `docs/decisions/README.md` and `docs/current/STATUS_REPORT.md` so the new structure proposal is discoverable from the active docs surface
