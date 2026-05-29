# Lab Meeting 2026-05-31: Startup and Dataset Panel Loading

Prepared on: `2026-05-29`

## Question

Should XBrainLab wait until the Dataset panel is fully loaded before showing the main window?

## Recommendation

No. Show the main window quickly, then materialize the Dataset workspace only after an explicit user
action.

The product problem is not only total startup time. It is also first visible feedback. A black
screen or frozen splash makes the app feel broken. A fast shell plus a stable Dataset entry state
feels responsive while still allowing heavier workflow tools to load only when needed.

## Current Data

The latest import-boundary cleanup made the Dataset path much lighter. The important point is that
the improvement comes from removing eager imports, not only from hiding work behind background
prewarm.

| Measurement | Result | Meaning |
| --- | ---: | --- |
| Dataset panel import, cold subprocess median / max | `0.360s` / `0.502s` | Import no longer pulls training, torch, sklearn, MNE, Data Import dialogs, or visualization stacks. |
| DatasetPanel creation after import median / max | `0.033s` / `0.037s` | Empty panel construction is light. |
| Cold materialize median / max | `0.422s` / `0.450s` | Dataset panel can be built without a multi-second block. |
| MainWindow product first-open without prewarm median / max | `0.312s` / `0.327s` | First Dataset view is under the product threshold without counting prewarm as the fix. |
| Default startup heartbeat max gap | `0.212s`, `0.013s`, `0.011s` | Startup remains below the `0.250s` UI-thread blocking gate when Dataset is user-triggered. |

Verification notes:

- `backend.application` package root is now a lazy public contract.
- Dataset panel / sidebar / action import no longer eager-load Data Import dialogs.
- `ui.dialogs.dataset` and `ui.components` expose lazy package exports.
- `ApplicationService` command routing no longer constructs training / analysis / interpretation
  service stacks just to answer state or capability queries.
- Real `MainWindow(Study()).switch_page(0)` no longer imports `mne`, `backend.load_data`, or
  `backend.preprocessor` on first Dataset open.
- Default startup no longer schedules Dataset panel materialization on a timer or after prewarm
  completion.
- The startup placeholder says `Dataset is ready to open.` and provides `Open Dataset`.

## Decision

Use this behavior for the MVP line:

1. Show the main window shell as soon as it is ready.
2. Keep Dataset selected by default, but show the lightweight `Open Dataset` entry state first.
3. Build Dataset lazily and avoid importing heavy workflow stacks until the user invokes them.
4. If a future machine or packaging path makes Dataset materialization visible again, show a
   Dataset-specific loading state after the explicit `Open Dataset` action instead of blocking the
   whole app.

Do not block the entire app until every Dataset tool is fully loaded. That would reintroduce the old
"nothing is happening" startup feeling.

## Dataset Loading UX Target

If a loading state is needed, it should look intentional:

- Title: `Preparing Dataset workspace`
- One-line status: `Loading import tools and dataset summary...`
- Stable layout matching the final Dataset panel footprint.
- No empty black area.
- No fake table rows.
- Navigation remains visible.

## Current Answer

The target startup model is:

`fast shell -> Open Dataset entry state -> user-triggered Dataset materialization -> workflow-specific tools load on demand`

This keeps startup responsive and fixes the original Dataset delay at the import boundary instead
of relying on background loading as a cosmetic workaround.
