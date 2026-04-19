# XBrainLab UI Baseline

This document defines the first-pass UI baseline for stabilization work.

It is not a design spec. It is a practical checklist for deciding whether the current PyQt UI is behaving and laying out acceptably while we repair the application.

## Design Change Rule

Some parts of the current UI are already considered satisfactory by the user.

Because of that:

- bug fixes and clarity fixes are allowed
- layout breakage should be corrected
- intentional visual redesign or layout restructuring should be discussed with the user first

This project is currently in stabilization mode, not open-ended redesign mode.

## Baseline Purpose

We need a shared answer to this question:

"When we change the code, how do we know the UI is still structurally intact?"

This file provides that answer at a simple, screen-by-screen level.

## Current Source Of Truth

The current UI baseline has three layers, and each layer serves a different purpose:

1. `docs/workflows/UI_BASELINE.md`
   - the human-readable definition of what "structurally correct" means
2. `artifacts/ui/`
   - the latest live screenshots captured during validation runs
3. `tests/baselines/ui/`
   - the reserved location for future approved reference screenshots

Right now, the authoritative definition of "correct" is still this document's checklist plus the latest live captures.

That means the current baseline proves things like:

- the shell and primary panels render
- controls remain visible
- navigation state matches the visible panel
- the AI assistant open state is still structurally sane

It does not yet prove:

- exact screenshot-level equivalence against a frozen golden image set
- pixel-perfect stability of spacing, alignment, or rendering details

So the current baseline is a stabilization baseline, not yet a full visual-regression baseline.

## Core Screens

These screens form the minimum baseline:

1. Main window shell
2. Dataset panel
3. Preprocess panel
4. Training panel
5. Evaluation panel
6. Visualization panel
7. AI assistant toggle and panel

## Main Window Shell Checklist

Expected baseline:

- window opens without crash
- top navigation bar is visible
- five navigation buttons are present
- `Dataset` is selected by default
- `AI Assistant` button is visible and toggleable
- central stacked area is visible and not collapsed
- no obvious empty white blocks, clipped bars, or overlapping shell controls

## Panel Checklist

Apply this checklist to each primary panel:

- panel opens from navigation without error
- primary controls are visible
- labels and buttons are not clipped at default window size
- no major section overlaps another
- panel refresh does not destroy prior state unexpectedly
- disabled/enabled states feel coherent for the current workflow stage

## Dialog Checklist

For high-use dialogs, validate:

- dialog opens and closes cleanly
- default buttons are visible
- form labels line up reasonably
- confirm/cancel actions do not hang
- validation feedback is visible when inputs are invalid

## Priority Screens For Screenshot Baseline

When we start capturing artifacts, prioritize:

- initial main window
- each top-level panel after first render
- one representative dataset dialog
- one representative training dialog
- one representative visualization screen

## Layout Defects To Treat As Real Bugs

These should be treated as genuine defects, not cosmetic trivia:

- clipped action buttons
- invisible or unreadable labels
- overlapping widgets
- dock/panel sections collapsing unintentionally
- navigation state not matching the visible panel
- modal dialogs opening off-size or without actionable controls

## Layout Defects To Triage Separately

These still matter, but can be triaged after stabilization basics:

- minor spacing inconsistency
- non-critical color mismatch
- slightly uneven alignment with no functional impact

## Suggested Artifact Workflow

Use an artifact folder when capturing baseline evidence:

```text
artifacts/ui/
```

Suggested naming:

- `main-window-initial.png`
- `panel-dataset.png`
- `panel-preprocess.png`
- `panel-training.png`
- `panel-evaluation.png`
- `panel-visualization.png`
- `ai-assistant-open.png`

Suggested capture command family:

```bash
mkdir -p artifacts/ui
```

Capture automation can be added later, but the folder convention should stay stable.

Current helper:

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py
```

The helper currently captures the shell plus the five primary panels into
`artifacts/ui/`, plus `ai-assistant-open.png` for the dock-open shell state.

Approved reference screenshots should not overwrite those live artifacts.
When we start promoting accepted screenshots into durable regression references,
store them under `tests/baselines/ui/`.

## Next Step

The first version of this baseline is checklist-based.

The next upgrade should be:

1. capture real screenshots for the core screens
2. promote approved screenshots into `tests/baselines/ui/`
3. keep fresh live validation evidence under `artifacts/ui/`
4. annotate known acceptable skips for visualization-heavy screens
5. use them during bug-fix review and dashboard refreshes
