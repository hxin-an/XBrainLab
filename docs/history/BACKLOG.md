# XBrainLab Stabilization Backlog

This is the initial prioritized backlog for takeover and repair work.

It is intentionally biased toward reducing uncertainty and increasing repair safety before deeper code changes.

## Now

### BL-000 Establish Codex harness and prep gate

- Priority: P0
- Why now:
  Long-running unattended work needs durable repo docs, a stable local Codex setup, and an explicit prep gate before deeper repair loops are safe.
- Outputs:
  - short `AGENTS.md`
  - `.agents/stack.md`
  - `.agents/runbooks/setup.md`
  - two-phase `.agents/runbooks/autopilot.md`
  - `.agents/skills/xbrainlab-prep-gate`
  - `.agents/skills/xbrainlab-repair-loop`
  - Docs MCP local configuration
  - thread heartbeat automation alignment
- Status:
  In progress.

### BL-001 Build dialog-level workflow coverage map

- Priority: P1
- Why now:
  We already know the app is dialog-heavy. We need a per-workflow list of the highest-value dialogs before fixing bugs in them.
- Outputs:
  - expand `docs/workflows/WORKFLOWS.md`
  - identify the top validation path for each workflow
  - maintain `docs/workflows/DIALOG_MATRIX.md`

### BL-002 Convert known risk clusters into concrete bug candidates

- Priority: P1
- Why now:
  Risk clusters are useful, but the next step is turning them into specific repairable items.
- Outputs:
  - expand `docs/current/BUG_TRIAGE.md`
  - create first batch of confirmed bug IDs

### BL-003 Create an artifacts path and screenshot capture routine

- Priority: P1
- Why now:
  Current tests cover behavior better than layout. We need visual evidence for future UI work.
- Outputs:
  - create `artifacts/ui/`
  - document the capture commands
  - capture baseline shell and panel screenshots
- Status:
  Done. The helper now captures the main shell, all five primary panels, and the AI assistant open state into `artifacts/ui/`.

### BL-004 Stabilize local validation commands in the current Codex workspace

- Priority: P1
- Why now:
  In the current `/mnt/d/repos/XBrainLab` workspace, default `pytest` capture is not yet reliable enough for unattended validation.
- Outputs:
  - confirm the failure mode
  - document the temporary `--capture=sys` workaround
  - triage or repair the capture teardown issue
- Status:
  In progress. The current blocker is now better narrowed: unattended UI pytest needs explicit offscreen Qt and writable matplotlib-cache env, and `scripts/dev/run_ui_pytest.sh` now captures that workaround. The older `fd`-capture teardown issue remains triage-only until it is either re-confirmed or retired.

### BL-015 Add a live quality dashboard for stabilization monitoring

- Priority: P1
- Why now:
  As stabilization work accumulates, we need one repeatable answer to whether startup, UI baseline, UI test slices, and real-data IO are still healthy.
- Outputs:
  - repo-local dashboard generator
  - stable human-facing dashboard entry doc
  - ignored live dashboard artifacts under `artifacts/quality/`
  - recurring automation refresh path
- Status:
  In progress. The dashboard generator and human entry doc are in place; the next step is keeping it refreshed automatically via the existing heartbeat loop.

## Soon

### BL-005 Verify top-level panel happy paths manually in headless display

- Priority: P1
- Scope:
  Dataset, Preprocess, Training, Evaluation, Visualization, AI shell
- Goal:
  turn workflow map assumptions into observed runtime facts
- Status:
  Done. Headless integration evidence now covers panel navigation plus AI dock toggling, and the baseline helper captures matching shell artifacts.

### BL-006 Add smoke tests for refresh and navigation behavior

- Priority: P1
- Why:
  Shared refresh coupling is one of the largest systemic risks
- Target areas:
  - `MainWindow.switch_page()`
  - panel `update_panel()` behavior
  - state synchronization after controller events
  - reference `docs/workflows/COVERAGE_GAPS.md`
- Status:
  Done. Main-window refresh/navigation smoke coverage remains in `tests/unit/ui/test_main_window_sync.py`, and `tests/unit/ui/test_panel_event_bridges.py` now covers the highest-value downstream event propagation paths.

### BL-007 Audit dialog acceptance flows for silent state loss

- Priority: P1
- Why:
  Many dialogs are mocked in tests, which lowers confidence in real modal workflows
- Target areas:
  - dataset label flows
  - preprocess operation dialogs
  - training setup dialogs
  - visualization settings/export dialogs
- Status:
  In progress. The prep-gate priority four (`LabelMappingDialog`, `EventFilterDialog`, `EpochingDialog`, `TrainingSettingDialog`) now have headless acceptance coverage in `tests/integration/ui/test_dialog_acceptance.py`; visualization/export and secondary dialogs remain follow-up territory only if new evidence points there.

## Later

### BL-008 Stabilize visualization validation strategy

- Priority: P2
- Goal:
  define a realistic approach for VTK/PyVista-heavy verification in this environment

### BL-009 Improve observability for multi-step UI actions

- Priority: P2
- Goal:
  add targeted logs or debug breadcrumbs where current state transitions are hard to inspect
- Status:
  In progress. `load_gdf_file()` now emits an explicit repo-level warning when real GDF import depends on MNE auto-renaming duplicate channel names.

### BL-010 Review AI assistant shell integration quality

- Priority: P2
- Goal:
  verify initialization, dock state, and model-switch behavior after core workflows are stabilized
- Status:
  Moved up by new runtime evidence. The shell now has a confirmed local-startup issue in the current environment, the first-start config sync, dependency preflight, and CUDA-device fallback path have been hardened, and the user has approved redesign of the AI assistant panel if needed. The current product direction is local-only startup rather than Gemini fallback.

### BL-011 Consolidate thesis-facing design docs for the agent redesign

- Priority: P1
- Why now:
  The repository has many design notes, but the master's-thesis direction needs a smaller and more explicit decision path before the agent redesign starts in earnest.
- Outputs:
  - a clear `docs/decisions/` entry point
  - one active thesis-direction ADR
  - one active product-definition ADR for the in-app assistant
  - clearer separation between active docs and historical reference docs
- Status:
  In progress.

### BL-014 Audit the in-app assistant tool surface against the new product definition

- Priority: P1
- Why now:
  The project now has a sharper definition of the in-app assistant as a workflow-aware software-operation agent sharing the same capability surface as the human user.
  The next design step is to check whether the current tool surface actually matches that definition.
- Outputs:
  - map the current tool surface
  - identify tool boundaries that are implementation-shaped instead of workflow-shaped
  - decide what should be merged, removed, or redesigned
  - define confirmation and observability requirements per tool group
- Status:
  Ready after the current documentation alignment finishes.

### BL-012 Redesign repository information architecture and doc system

- Priority: P1
- Why now:
  The current repository has reached the point where active docs, historical notes, and reference material compete for attention, which will slow both stabilization work and the thesis-era agent redesign.
- Outputs:
  - one approved target repository structure
  - one approved target `docs/` structure
  - a migration plan for active, guide, api, and archived docs
  - a root-level entry strategy including `README.md` and updated published-doc navigation
- Status:
  In progress. The new root `README.md`, `docs/guides/`, `docs/archive/`, and updated navigation have been created; remaining work is secondary cleanup and archive slimming.

## Deferred Until After Triage

### BL-013 Large architectural refactors

- Priority: P3
- Examples:
  - broad panel rewrites
  - redesigning controller boundaries wholesale
  - changing multiple workflow surfaces in one pass

- Reason for deferral:
  we need more observed evidence before reshaping architecture
