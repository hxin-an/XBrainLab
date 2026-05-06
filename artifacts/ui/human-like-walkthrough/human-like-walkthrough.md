# Human-Like Product Walkthrough

- status: `passed`
- failure reason: none
- claim boundary: Automated UI-observable PyQt replay; not human Windows desktop acceptance. Windows launcher click-through, dual-monitor/DPI behavior, and long real local-model desktop sessions remain human verification.
- elapsed seconds: `4.759`
- source: `<walkthrough_source>`
- recipe: `artifacts/ui/human-like-walkthrough/walkthrough-import.recipe.json`

## Pass / Fail

- passed: `True`
- phases: `26` / `26`
- screenshots: `20`
- human desktop acceptance: `not performed`
- resource smoke passed: `True`
- RSS growth: `230244` KB / limit `600000` KB

## Screenshots

- main_initial: `artifacts/ui/human-like-walkthrough/01-main-initial.png`
- dataset_page: `artifacts/ui/human-like-walkthrough/02-dataset-page.png`
- source_selection: `artifacts/ui/human-like-walkthrough/03-source-selection.png`
- wizard_preview: `artifacts/ui/human-like-walkthrough/04-interpretation-preview.png`
- wizard_confirm: `artifacts/ui/human-like-walkthrough/05-interpretation-confirm.png`
- applied: `artifacts/ui/human-like-walkthrough/06-interpretation-applied.png`
- recipe_reloaded: `artifacts/ui/human-like-walkthrough/07-recipe-reloaded.png`
- preprocess: `artifacts/ui/human-like-walkthrough/08-preprocessing.png`
- dataset_ready: `artifacts/ui/human-like-walkthrough/09-dataset-ready.png`
- training_readiness: `artifacts/ui/human-like-walkthrough/10-training-readiness.png`
- analysis_readiness: `artifacts/ui/human-like-walkthrough/11-analysis-readiness.png`
- assistant_empty: `artifacts/ui/human-like-walkthrough/12-assistant-empty.png`
- assistant_normal: `artifacts/ui/human-like-walkthrough/13-assistant-normal.png`
- assistant_clarification: `artifacts/ui/human-like-walkthrough/14-assistant-clarification.png`
- assistant_blocked: `artifacts/ui/human-like-walkthrough/15-assistant-blocked.png`
- assistant_success: `artifacts/ui/human-like-walkthrough/16-assistant-success.png`
- assistant_narrow: `artifacts/ui/human-like-walkthrough/17-assistant-narrow.png`
- reset_boundary: `artifacts/ui/human-like-walkthrough/18-reset-boundary.png`
- error_recovery: `artifacts/ui/human-like-walkthrough/19-error-recovery.png`
- eval_dashboard: `artifacts/ui/human-like-walkthrough/20-eval-dashboard.png`

## UI Quality Review

- automated checks passed: `True`
- phase snapshot coverage: `True`
- forbidden visible text findings: `0`
- human review boundary: This is automated UI-observable evidence. It does not replace a human desktop review of Windows launcher, dual-monitor/DPI, or long local-model sessions.
- table geometry passed: `True`
- checked table/tree widgets: `18`
- table geometry findings: `0`
- clipped row findings: `0`

## Observable Evidence

- visible text snapshots: `26` phases
- button states: `26` phases
- workflow/backend snapshots: `26` phases
- UI geometry snapshots: `6` phases

## Phases

- `app_startup` -> `artifacts/ui/human-like-walkthrough/01-main-initial.png`
- `main_window_initial_state` -> `artifacts/ui/human-like-walkthrough/02-dataset-page.png`
- `data_source_selection` -> `artifacts/ui/human-like-walkthrough/03-source-selection.png`
- `data_interpretation_select_source` -> `artifacts/ui/human-like-walkthrough/03-source-selection.png`
- `data_interpretation_scan_result` -> `artifacts/ui/human-like-walkthrough/04-interpretation-preview.png`
- `data_interpretation_preview` -> `artifacts/ui/human-like-walkthrough/05-interpretation-confirm.png`
- `data_interpretation_confirm_metadata_labels` -> `artifacts/ui/human-like-walkthrough/05-interpretation-confirm.png`
- `data_interpretation_decisions` -> `artifacts/ui/human-like-walkthrough/06-interpretation-applied.png`
- `data_interpretation_apply` -> `artifacts/ui/human-like-walkthrough/06-interpretation-applied.png`
- `data_interpretation_save_recipe` -> `artifacts/ui/human-like-walkthrough/06-interpretation-applied.png`
- `data_interpretation_reload_recipe` -> `artifacts/ui/human-like-walkthrough/07-recipe-reloaded.png`
- `preprocessing` -> `artifacts/ui/human-like-walkthrough/08-preprocessing.png`
- `epoch_creation` -> `artifacts/ui/human-like-walkthrough/09-dataset-ready.png`
- `dataset_generation` -> `artifacts/ui/human-like-walkthrough/09-dataset-ready.png`
- `training_readiness` -> `artifacts/ui/human-like-walkthrough/10-training-readiness.png`
- `evaluation_visualization_saliency_readiness` -> `artifacts/ui/human-like-walkthrough/11-analysis-readiness.png`
- `assistant_empty_state` -> `artifacts/ui/human-like-walkthrough/12-assistant-empty.png`
- `assistant_repeated_open_close` -> `artifacts/ui/human-like-walkthrough/12-assistant-empty.png`
- `assistant_normal_message` -> `artifacts/ui/human-like-walkthrough/13-assistant-normal.png`
- `assistant_missing_input_clarification` -> `artifacts/ui/human-like-walkthrough/14-assistant-clarification.png`
- `assistant_blocked_command` -> `artifacts/ui/human-like-walkthrough/15-assistant-blocked.png`
- `assistant_successful_tool_result` -> `artifacts/ui/human-like-walkthrough/16-assistant-success.png`
- `assistant_narrow_panel` -> `artifacts/ui/human-like-walkthrough/17-assistant-narrow.png`
- `reset_new_session_boundary` -> `artifacts/ui/human-like-walkthrough/18-reset-boundary.png`
- `error_recovery` -> `artifacts/ui/human-like-walkthrough/19-error-recovery.png`
- `eval_dashboard_report` -> `artifacts/ui/human-like-walkthrough/20-eval-dashboard.png`

## User-Facing Transcript

- user: Hello.
- assistant: I can help interpret EEG data and prepare a training-ready dataset.
- user: Load my brainwave data.
- assistant: Choose a file, folder, BIDS root, or saved recipe before I can scan it.
- user: Train it now.
- assistant: Training is not ready until data, epochs, a dataset, a model, and settings are ready.
- user: What is ready now?
- assistant: The dataset and training settings are ready; evaluation needs a completed run.
- user: Preview the selected data again.
- assistant: I need a source scan before previewing. I scanned the selected source again.

## Command / Tool Transcript

- `scan_source`: `ok` - Scanned source and found 2 EEG file(s).
- `preview_interpretation`: `ok` - Interpretation preview ready.
- `validate_interpretation`: `ok` - Interpretation validation: needs_confirmation.
- `preview_interpretation`: `ok` - Interpretation preview ready.
- `validate_interpretation`: `ok` - Interpretation validation: needs_confirmation.
- `apply_interpretation`: `failed` - apply_interpretation requires confirmation.
- `apply_interpretation`: `ok` - Applied interpretation and loaded 2 file(s). Imported reviewed labels for 1 file(s).
- `save_interpretation_recipe`: `ok` - Interpretation recipe saved.
- `reload_interpretation_recipe`: `ok` - Interpretation recipe reloaded for review.
- `preprocess`: `ok` - Standard preprocessing applied.
- `create_epoch`: `ok` - Created epochs from 0.0s to 1.0s.
- `generate_dataset`: `ok` - Generated 1 dataset(s).
- `configure_training`: `ok` - Training configured.
- `evaluate`: `failed` - Create a training plan before evaluating results.
- `visualize`: `ok` - Visualization summary ready.
- `saliency`: `ok` - Saliency parameters are not configured yet.
- `query_state`: `ok` - Application state snapshot ready.
- `new_session`: `failed` - new_session requires confirmation.
- `new_session`: `ok` - New session started.
- `preview_interpretation`: `failed` - Scan a data source before previewing interpretation.
- `scan_source`: `ok` - Scanned source and found 2 EEG file(s).

## Resource Notes

- smoke checked: `True`
- smoke passed: `True`
- boundary: Coarse process smoke only: RSS uses ru_maxrss high-water mark and this does not prove the absence of leaks.
- start: threads `1`, qt active `0`, rss `836668` KB
- before_close: threads `1`, qt active `0`, rss `1066912` KB
- after_close: threads `1`, qt active `0`, rss `1066912` KB

## Remaining Human Verification

- Windows desktop launcher click-through
- dual-monitor and DPI behavior
- long real local-model desktop session
