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
  - document the temporary `-s` workaround
  - triage or repair the capture teardown issue
- Status:
  In progress.

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
  In progress. Main-window refresh/navigation smoke coverage has been expanded in `tests/unit/ui/test_main_window_sync.py`, and existing refresh integration coverage still passes.

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
  In progress. `ImportLabelDialog` no longer assumes numeric-only sequence labels, but the rest of the label dialog stack still needs runtime-oriented audit.

## Later

### BL-008 Stabilize visualization validation strategy

- Priority: P2
- Goal:
  define a realistic approach for VTK/PyVista-heavy verification in this environment

### BL-009 Improve observability for multi-step UI actions

- Priority: P2
- Goal:
  add targeted logs or debug breadcrumbs where current state transitions are hard to inspect

### BL-010 Review AI assistant shell integration quality

- Priority: P2
- Goal:
  verify initialization, dock state, and model-switch behavior after core workflows are stabilized
- Status:
  Moved up by new runtime evidence. The shell now has a confirmed local-initialization failure in the current environment, and the user has approved redesign of the AI assistant panel if needed.

## Deferred Until After Triage

### BL-011 Large architectural refactors

- Priority: P3
- Examples:
  - broad panel rewrites
  - redesigning controller boundaries wholesale
  - changing multiple workflow surfaces in one pass

- Reason for deferral:
  we need more observed evidence before reshaping architecture
