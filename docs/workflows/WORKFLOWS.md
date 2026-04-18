# XBrainLab Workflow Map

This document maps the main user workflows based on the current code structure.

It is written for takeover and bug-fix work, not end-user documentation.

## Workflow Philosophy

Most workflows in this application follow the same broad shape:

1. user action begins in a panel or dialog
2. the panel calls a controller
3. backend state changes in `Study` or delegated managers
4. observer events are emitted
5. panels refresh themselves through `update_panel()` or a more specific update path

This makes refresh bugs and state-sync bugs especially important.

## Main Window Shell

File:

- `XBrainLab/ui/main_window.py`

Responsibilities:

- create the top-level navigation shell
- build five primary panels
- switch stacked pages
- call `update_panel()` when the active page changes
- initialize the AI assistant system

Risk notes:

- panel switching logic is centralized here
- if navigation state or panel refresh behavior breaks, many workflows can appear broken at once

## Workflow 1: Dataset Intake

Primary files:

- `XBrainLab/ui/panels/dataset/panel.py`
- `XBrainLab/ui/panels/dataset/sidebar.py`
- `XBrainLab/ui/panels/dataset/actions.py`

User intent:

- load EEG files
- inspect loaded file metadata
- import labels
- adjust subject/session metadata
- trigger dataset-related helper actions

Observed panel behavior:

- left side is a table of loaded files
- right side is a sidebar for operations and info
- panel listens to `data_changed` and `import_finished`
- table edits for subject/session call back into the controller

Likely bug surfaces:

- metadata edits not persisting or not refreshing correctly
- import completion not updating UI consistently
- table and sidebar summaries drifting out of sync

Key dialogs and interactions:

- file picker via `QFileDialog.getOpenFileNames()`
- `SmartParserDialog`
- `ImportLabelDialog`
- `LabelMappingDialog`
- `EventFilterDialog`
- table context menu for batch subject/session edit and file removal

Primary happy path:

1. import one or more EEG files
2. wait for `import_finished`
3. verify table rows and sidebar summary update
4. optionally run smart parse for filename-derived metadata
5. optionally import labels and apply event filtering
6. confirm metadata edits persist and table refresh remains coherent

## Workflow 2: Preprocess

Primary files:

- `XBrainLab/ui/panels/preprocess/panel.py`
- `XBrainLab/ui/panels/preprocess/sidebar.py`
- `XBrainLab/ui/panels/preprocess/preview_widget.py`
- `XBrainLab/ui/panels/preprocess/history_widget.py`

User intent:

- preview signals
- apply preprocessing steps
- inspect preprocessing history

Observed panel behavior:

- preview area and history live on the left
- operation controls live in the sidebar
- panel listens to both preprocess events and dataset events
- epoched data locks parts of preprocessing with a locked message

Likely bug surfaces:

- preview widgets not matching current dataset state
- channel selector or time-range controls drifting after data changes
- locked/unlocked preprocess state not reflecting actual backend state

Key dialogs and interactions:

- `FilteringDialog`
- `ResampleDialog`
- `RereferenceDialog`
- `NormalizeDialog`
- `EpochingDialog`
- reset preprocessing action

Primary happy path:

1. load data from Dataset workflow
2. open preview and verify channel/time controls populate
3. apply one or more preprocessing operations
4. verify history updates after each step
5. run epoching
6. confirm panel enters locked state and communicates that clearly

## Workflow 3: Training Setup And Monitoring

Primary files:

- `XBrainLab/ui/panels/training/panel.py`
- `XBrainLab/ui/panels/training/sidebar.py`
- `XBrainLab/ui/panels/training/history_table.py`

User intent:

- configure model and training options
- start and stop training
- monitor plots, logs, and run history

Observed panel behavior:

- metric plots and logs live in tabbed views
- training history is tracked in a dedicated table
- sidebar owns most configuration and execution controls
- panel listens to training lifecycle events and dataset changes

Likely bug surfaces:

- training state not reflected correctly in buttons or logs
- history selection not syncing to plots
- ready-to-train checks disagreeing with actual backend readiness

Key dialogs and interactions:

- `DataSplittingDialog`
- `ModelSelectionDialog`
- `TrainingSettingDialog`
- start/stop training controls
- clear-history flow

Primary happy path:

1. confirm epoched data exists
2. configure dataset splitting
3. configure model
4. configure training settings
5. verify start button becomes enabled
6. launch training
7. watch plots, logs, and history update
8. stop or complete training and confirm downstream screens refresh

## Workflow 4: Evaluation

Primary files:

- `XBrainLab/ui/panels/evaluation/panel.py`
- `XBrainLab/ui/panels/evaluation/confusion_matrix.py`
- `XBrainLab/ui/panels/evaluation/metrics_table.py`
- `XBrainLab/ui/panels/evaluation/metrics_bar_chart.py`

User intent:

- inspect confusion matrices
- compare per-class metrics
- review model summaries

Observed panel behavior:

- content depends on available training plans and runs
- panel reacts to `training_stopped`
- supports per-run and averaged finished-run views

Likely bug surfaces:

- combo boxes not reflecting actual available plans/runs
- stale summary text after selection changes
- mismatches between matrix, metrics table, and selected record

Key interactions:

- select fold/plan from combo
- select specific run or averaged finished runs
- toggle percentage display
- inspect confusion matrix, metrics table, bar chart, and summary text together

Primary happy path:

1. complete at least one training run
2. open Evaluation panel
3. verify available folds appear
4. switch between run-specific and averaged views
5. confirm matrix, metrics table, bar chart, and summary stay in sync

## Workflow 5: Visualization

Primary files:

- `XBrainLab/ui/panels/visualization/panel.py`
- `XBrainLab/ui/panels/visualization/control_sidebar.py`
- `XBrainLab/ui/panels/visualization/saliency_views/*`

User intent:

- inspect saliency maps
- switch between map, spectrogram, topographic, and 3D views
- choose plan, run, method, and absolute-value mode

Observed panel behavior:

- unified control bar drives all visualization tabs
- plan selection repopulates run selection
- current tab and selected run determine the rendered view

Likely bug surfaces:

- combo refresh logic failing when training outputs change
- rendering-specific crashes or empty-state confusion
- headless-only versus real-GUI discrepancies

Key dialogs and interactions:

- `PickMontageDialog`
- `SaliencySettingDialog`
- `ExportSaliencyDialog`
- plan/run/method combo coordination
- tab switching across map, spectrogram, topographic map, and 3D plot

Primary happy path:

1. complete training and generate selectable trainer outputs
2. open Visualization panel
3. choose plan and run
4. switch saliency method and absolute mode
5. verify each tab renders a meaningful state or a clear empty-state message
6. set montage or saliency settings
7. export saliency when data is available

## Workflow 6: AI Assistant

Primary files:

- `XBrainLab/ui/components/agent_manager.py`
- `XBrainLab/ui/chat/panel.py`
- related `XBrainLab/llm/*`

User intent:

- toggle the assistant
- interact with backend workflows through the agent

Observed shell behavior:

- AI assistant is initialized from `MainWindow`
- status messages are routed back into the shell

Likely bug surfaces:

- initialization timing
- dock visibility/state mismatches
- agent actions changing backend state without the expected panel refresh

Key dialogs and interactions:

- `ModelSettingsDialog`
- dock show/hide and float toggle
- new conversation button
- model-switch and execution-mode changes

Primary happy path:

1. open AI assistant from the main shell
2. accept model/settings setup
3. send a user message
4. verify assistant response, status updates, and dock state
5. switch or reopen the dock without losing UI coherence

## Shared Bug Patterns To Watch

Across the workflows above, these patterns are especially likely:

- controller event emitted but panel does not refresh
- panel refreshes but uses stale selection state
- sidebar and main content disagree
- headless tests pass while real UI layout is still wrong
- user-triggered dialog flow succeeds logically but leaves UI in inconsistent state

## Next Workflow Tasks

The next useful expansion of this document is:

1. list the top dialogs under each workflow
2. record the most important happy-path sequence for each workflow
3. attach confirmed bug IDs from `docs/current/BUG_TRIAGE.md`

Related dialog inventory:

- `docs/workflows/DIALOG_MATRIX.md`
