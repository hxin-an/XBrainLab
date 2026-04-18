# XBrainLab Risk Clusters

This document groups the highest-risk bug and maintenance areas discovered during takeover work.

The goal is to help sequence repairs intelligently instead of treating all bugs as equal.

## Cluster 1: Event-Driven Refresh Coupling

Why it matters:

- the UI depends heavily on observer bridges
- many panels refresh from shared events such as `data_changed`, `import_finished`, and `training_stopped`
- a single broken event path can make the UI look stale or inconsistent even when backend state is correct

Observed signals:

- every main panel registers bridges through `BasePanel._create_bridge()`
- `MainWindow.switch_page()` also calls `update_panel()` directly when navigating
- shared UI freshness depends on both event delivery and page-switch refresh logic

Typical symptoms:

- panel appears stale after backend action
- sidebar and main content disagree
- switching away and back "fixes" the UI

Suggested repair posture:

- treat refresh bugs as infrastructure issues first, not panel-only issues
- add focused tests around event-driven update behavior before broad refactors

## Cluster 2: Visualization And Rendering Fragility

Why it matters:

- visualization is the most environment-sensitive area
- VTK/PyVista behavior is already known to be unstable in headless runs
- rendering issues are likely to escape the default fast suite

Observed signals:

- headless UI suite passes with visualization-related skips
- test files repeatedly reference headless instability and segfault risk
- visualization panel contains multiple rendering modes with plan/run/method coordination

Typical symptoms:

- tab renders empty or errors for a valid selection
- combo state does not match actual available outputs
- tests pass while real GUI rendering is still broken

Suggested repair posture:

- isolate visualization fixes
- validate with focused manual evidence and artifacts
- avoid mixing visualization changes with unrelated shell/panel refactors

## Cluster 3: Training State Synchronization

Why it matters:

- training touches plots, logs, history, readiness, evaluation, and visualization
- training events fan out into multiple screens

Observed signals:

- `TrainingPanel` listens to many lifecycle events
- `EvaluationPanel` and `VisualizationPanel` both update off training completion
- readiness and configuration logic partly lives in the training sidebar

Typical symptoms:

- train/stop buttons in the wrong state
- history table and plots showing different records
- evaluation or visualization combos not updating after a completed run

Suggested repair posture:

- triage training bugs as cross-workflow issues
- always validate downstream screens after changing training state logic

## Cluster 4: Dialog-Heavy Workflow Surface

Why it matters:

- this app exposes many dialogs across dataset, preprocess, training, and visualization
- dialog workflows are common places for silent state loss and blocked interactions

Observed signals:

- many feature areas depend on modal dialogs
- tests globally patch dialog execution to avoid hangs

Typical symptoms:

- dialog accepts but changes do not propagate
- invalid inputs close too easily or fail without clear feedback
- tests pass because blocking dialogs are mocked, while live UX still misbehaves

Suggested repair posture:

- treat dialogs as workflow boundaries, not trivial UI details
- pair behavior tests with manual validation notes when touching modal flows

## Cluster 5: Documentation And Runtime Reality Drift

Why it matters:

- existing docs include historical status and ambitious quality claims
- takeover work needs current facts, not inherited optimism

Observed signals:

- current local UI baseline is verified in WSL2
- known-issues docs read partly as release history, not current repair backlog
- test architecture docs are useful, but not always aligned with real current priorities

Typical symptoms:

- team assumes a risk area is solved because docs say so
- bug prioritization follows old milestones instead of present pain

Suggested repair posture:

- keep takeover docs factual and date-stamped
- prefer runtime-verified notes over inherited status claims

## Recommended Fix Order

For stabilization work, the safest general order is:

1. shell and shared refresh plumbing
2. dataset and preprocess reliability
3. training state synchronization
4. evaluation consistency
5. visualization stabilization
6. agent-specific polish and deeper architecture cleanup
