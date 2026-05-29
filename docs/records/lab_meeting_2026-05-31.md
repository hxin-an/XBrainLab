# Lab Meeting 2026-05-31: Startup and Dataset Panel Loading

Prepared on: `2026-05-29`

## Question

Should XBrainLab wait until the Dataset panel is fully loaded before showing the main window?

## Recommendation

No. Show the startup splash quickly, use that splash phase to prepare the Dataset workspace, then
show the main window with Dataset already open.

The product problem is not only total startup time. It is also first visible feedback. A black
screen or frozen splash makes the app feel broken. But adding another `Open Dataset` step after
startup also makes the product feel harder to use. The right split is: the splash owns initial
Dataset preparation; the main window owns the real workflow.

## Current Data

The latest import-boundary cleanup made the Dataset path much lighter. The important point is that
the improvement comes from removing eager imports, not only from hiding work behind background
prewarm.

| Measurement | Result | Meaning |
| --- | ---: | --- |
| Dataset panel import, cold subprocess median / max | `0.360s` / `0.502s` | Import no longer pulls training, torch, sklearn, MNE, Data Import dialogs, or visualization stacks. |
| DatasetPanel creation after import median / max | `0.033s` / `0.037s` | Empty panel construction is light. |
| Cold materialize median / max | `0.422s` / `0.450s` | Dataset panel can be built without a multi-second block. |
| MainWindow product first-open without prewarm median / max | `0.312s` / `0.327s` | Dataset materialization is short enough to happen during splash instead of forcing a second user action. |

Verification notes:

- `backend.application` package root is now a lazy public contract.
- Dataset panel / sidebar / action import no longer eager-load Data Import dialogs.
- `ui.dialogs.dataset` and `ui.components` expose lazy package exports.
- `ApplicationService` command routing no longer constructs training / analysis / interpretation
  service stacks just to answer state or capability queries.
- Real `MainWindow(Study()).switch_page(0)` no longer imports `mne`, `backend.load_data`, or
  `backend.preprocessor` on first Dataset open.
- The startup splash now says `Preparing Dataset workspace...`.
- MainWindow materializes the Dataset panel before it is shown, while the splash is still visible.
- The main window no longer presents an extra `Open Dataset` step.

## Decision

Use this behavior for the MVP line:

1. Show the main window shell as soon as it is ready.
2. Use the startup splash for initial Dataset preparation.
3. Keep Dataset selected and ready when the main window appears.
4. Continue lazy-loading Data Import dialogs, training, visualization, and other heavier workflow
   tools until the user invokes them.

Do not block the entire app until every Dataset tool is fully loaded. That would reintroduce the old
"nothing is happening" startup feeling.

## Dataset Loading UX Target

If a fallback loading state is needed inside the main window, it should look intentional:

- Title: `Preparing Dataset workspace`
- One-line status: `Loading import tools and dataset summary...`
- Stable layout matching the final Dataset panel footprint.
- No empty black area.
- No fake table rows.
- Navigation remains visible.

## Current Answer

The target startup model is:

`splash -> prepare Dataset workspace -> main window with Dataset ready -> workflow-specific tools load on demand`

This keeps startup responsive and fixes the original Dataset delay at the import boundary instead
of relying on background loading as a cosmetic workaround.
