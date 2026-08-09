---
hide:
  - navigation
---

# XBrainLab

<p class="page-kicker">Local EEG workflow · development build</p>

<p class="portal-lede">Use the desktop app to review EEG data, prepare epochs,
configure a split and model, and inspect evaluation or visualization views. Start with
a reviewed import; each later stage depends on the decisions made before it.</p>

<div class="portal-actions">
  <div>
    <span class="action-label">New session</span>
    <strong>Set up and review your first import</strong>
    <p>Launch the development build, choose a small dataset scope, and confirm labels and metadata before continuing.</p>
    <a class="md-button md-button--primary" href="getting-started/">Start with setup</a>
  </div>
  <div>
    <span class="action-label">Returning user</span>
    <strong>Continue from the active checkpoint</strong>
    <p>Check the dependency order, stop conditions, and review values for the stage you are working in.</p>
    <a class="md-button" href="workflow/">Open the desktop workflow</a>
  </div>
</div>

<div class="status-strip status-strip--compact" markdown>
  <div>
    <span class="status-label">Distribution</span>
    <strong>Source-based development build; no signed installer</strong>
  </div>
  <div>
    <span class="status-label">Workflow available</span>
    <strong>Import, preprocess, epoch, split/train, evaluate, visualize</strong>
  </div>
  <div>
    <span class="status-label">Dataset evidence</span>
    <strong>All five run guides remain Unverified</strong>
  </div>
</div>

!!! warning "Dataset completion is not claimed"
    Neither the Graz nor OpenNeuro route publishes an identified manual run from import
    through saliency. The three MOABB routes are execution-pending guides, not completed
    runs. Every page remains **Unverified** until a manifest ID, app revision, run ID,
    and evidence files are published together.

<figure class="product-shot product-shot--wide desktop-shot" markdown>
  [![XBrainLab desktop application at the Dataset stage before EEG data is imported](assets/screenshots/desktop-start.png)](assets/screenshots/desktop-start.png)
  <figcaption>Open the image at full size. This is an empty Dataset view and does not show a completed dataset run.</figcaption>
</figure>

<div class="screen-checks" markdown>
  <strong>Check the desktop view</strong>

  - Top tabs: **Dataset**, **Preprocess**, **Training**, **Evaluation**, **Visualization**.
  - Dataset actions: **Import file**, **Import folder**, **Import BIDS**, **Reload recipe**.
  - Empty-state text: **No EEG data loaded**.
</div>

## One workflow, six checkpoints

These are product checkpoints. A dataset only advances when its own expected values are
reviewed and its stop conditions remain clear.

<ol class="workflow-rail">
  <li><strong>Interpret</strong><span>Choose scope, labels, and metadata; stop on an unexplained mismatch.</span></li>
  <li><strong>Preprocess</strong><span>Apply a study-specific operation and verify the visible history.</span></li>
  <li><strong>Epoch</strong><span>Choose an anchor and time window; check counts before continuing.</span></li>
  <li><strong>Split</strong><span>Hold out the unit required by the research question.</span></li>
  <li><strong>Train</strong><span>Bind model and settings to the selected dataset and split.</span></li>
  <li><strong>Inspect</strong><span>Read evaluation or saliency only for an identified trained run.</span></li>
</ol>

## What the desktop app is for

<div class="purpose-list" markdown>
  <div markdown>
  **Review data before analysis**

  Keep selected files, label carriers, subject/session/task/run metadata, and decisions
  visible before they become active workflow state.
  </div>
  <div markdown>
  **Run a dependency-ordered sequence**

  Preserve prerequisites while moving through preprocessing, epoching, dataset
  generation, training, evaluation, and visualization.
  </div>
  <div markdown>
  **Stop at the right boundary**

  Treat empty and blocked states as missing prerequisites. Reset or begin a new session
  when an earlier data decision must change.
  </div>
  <div markdown>
  **Keep the core workflow local**

  The optional local assistant is not required for import, preprocessing, training, or
  result review.
  </div>
</div>

## Choose a dataset run guide

These pages provide exact scopes and checkpoint instructions. They do not become
manual-completion evidence until their identity blocks are populated from a publishable
evidence manifest.

<div class="grid cards case-links route-cards" markdown>

-   **Graz / BCI Competition IV 2a**

    Page scenario: `A01T.gdf`, `A02T.gdf`, `A03T.gdf` with matching MAT label files.

    **Evidence identity:** Unverified.

    [Run the Graz route](case-studies/graz-2a.md)

-   **OpenNeuro ds003061 P300**

    Page scenario: `sub-001`, session `01`, task `P300`, runs `1`, `2`, and `3`.

    **Evidence identity:** Unverified.

    [Run the OpenNeuro route](case-studies/openneuro-ds003061.md)

-   **MOABB compact execution routes**

    Ofner2017 subject `1`, `imagination` runs `1`–`9`; PhysionetMI subject `1`
    runs `4` and `6`; Lee2021Mobile ERP subject `1`, session `01`, `task-ERP`.

    **Execution state:** Pending. **Evidence identity:** Unverified.

    [Review the three MOABB guides](case-studies/index.md)

</div>

!!! warning "Research interpretation remains your responsibility"
    XBrainLab can execute and display an analysis route. Protocol validity, leakage
    control, split design, preprocessing choices, statistical interpretation, and
    publication claims still require study-specific review. See [FAQ and Limits](faq-limits.md).

Maintainers can review project status, architecture, and validation in the
<a href="../">engineering documentation</a>.
