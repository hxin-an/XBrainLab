# XBrainLab Takeover Map

This document is the practical handoff map for stabilizing the current PyQt application.

It is intentionally narrower and more operational than the architecture docs. It focuses on what we need in order to fix bugs safely.

## Goal

Turn a large, bug-prone PyQt application into a project that is:

- runnable on demand
- understandable by module and workflow
- testable in headless WSL
- safe to change incrementally

## What We Verified

Verified locally on `2026-04-18`:

- `Poetry` environment installs successfully in WSL2
- `run.py` launches the app to main window startup
- `Study` import works
- `tests/unit/ui` passes in the current environment with `718 passed, 15 skipped`

This means the project is already past the "broken bootstrap" stage. We can now focus on controlled understanding and repair.

## Primary Runtime Entry

- GUI entrypoint: `run.py`
- top-level window: `XBrainLab/ui/main_window.py`
- application state root: `XBrainLab/backend/study.py`

## Practical Architecture View

The codebase is easiest to reason about in four layers:

1. Startup and shell
   - `run.py`
   - splash, app setup, CLI overrides, window creation

2. UI orchestration
   - `XBrainLab/ui/main_window.py`
   - panel switching, top navigation, AI toggle, agent bootstrapping

3. Feature panels and dialogs
   - `XBrainLab/ui/panels/*`
   - `XBrainLab/ui/dialogs/*`
   - this is where most user-visible bugs are likely to surface

4. Backend state and controllers
   - `XBrainLab/backend/*`
   - `Study`, controllers, managers, services

## Main User-Facing Areas

From `MainWindow`, the primary panel structure is:

- Dataset
- Preprocess
- Training
- Evaluation
- Visualization
- AI Assistant

The first five are added to the stacked main content area. The AI assistant is managed separately via `AgentManager`.

## High-Risk Zones

These areas deserve extra care because defects here can spread broadly:

- `XBrainLab/ui/main_window.py`
  - affects navigation, panel lifecycle, agent bootstrapping
- `XBrainLab/ui/core/*`
  - shared base classes and cross-panel infrastructure
- `XBrainLab/backend/study.py`
  - central state container and delegation root
- `XBrainLab/backend/controller/*`
  - business action dispatch path
- visualization-related UI and VTK/PyVista integration
  - more fragile in headless and test environments

## Current Testing Reality

The repository already has a lot of tests, but the real operational view is:

- UI unit tests are healthy in headless WSL
- some visualization tests are intentionally skipped in headless mode
- existing docs contain ambitious or historical quality numbers; treat them as directional, not authoritative
- `tests/conftest.py` applies global UI blocking patches and visualization mocks, so test behavior is intentionally not identical to a fully interactive desktop session

## Known Gaps For Takeover

These are the gaps we should close before heavy bug-fixing:

1. Workflow map
   - we still need a clean, explicit description of the major user flows

2. UI baseline
   - we do not yet have a screenshot or layout checklist for major screens

3. Bug inventory
   - known issues docs contain history, but not yet a current prioritized repair list for this takeover

4. Visual regression strategy
   - current tests focus mostly on behavior, not layout fidelity

## Recommended Takeover Sequence

1. Capture the real current workflows.
2. Define the UI baseline for the main screens.
3. Identify the top bug clusters.
4. Add targeted smoke tests for the riskiest flows.
5. Only then begin larger structural repairs.

## Initial Bug Buckets To Build

When triaging, classify issues into one of these buckets:

- startup and environment bugs
- panel navigation and refresh bugs
- dialog and form-state bugs
- backend-controller integration bugs
- visualization and rendering bugs
- agent and chat workflow bugs
- layout and visual consistency bugs

This classification will help us avoid mixing architecture work with straightforward UI fixes.

## Related Documents

- `docs/workflows/WORKFLOWS.md`
- `docs/current/BUG_TRIAGE.md`
- `docs/workflows/RISK_CLUSTERS.md`
- `docs/workflows/TESTING_STRATEGY.md`
- `docs/workflows/UI_BASELINE.md`
