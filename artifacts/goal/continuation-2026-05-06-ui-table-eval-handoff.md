# XBrainLab Product Completion Continuation - 2026-05-06 UI Table / Eval Gate

Use this as the next-run handoff for the active product-completion goal. Do not
mark Goal 1 product-complete while the blockers below remain.

## Current Repo / Branch

- Repo: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
- Branch: `codex/stabilization-autopilot`
- Do not push.
- Do not touch / stage / revert `.vscode/settings.json`, root `settings.json`, or the user-added
  `.agents/skills/*` changes unless the user explicitly asks.

Expected dirty files after this handoff:

```text
 M .agents/skills/README.md
 M .vscode/settings.json
 M settings.json
?? .agents/skills/clean-code-reviewer/
?? .agents/skills/data-interpretation-reviewer/
?? .agents/skills/mcp-adapter-reviewer/
?? .agents/skills/performance-resource-reviewer/
?? .agents/skills/release-packaging-reviewer/
?? .agents/skills/security-privacy-reviewer/
?? .agents/skills/thesis-evidence-reviewer/
?? .agents/skills/ui-product-reviewer/
```

## Latest Validated Commits

```text
9e3a8cb ui: guard dataset action fallback gates
5330278 docs: refresh handoff after preprocess fallback guard
cf831b2 ui: guard preprocess fallback gates
41a61d2 ui: guard dataset sidebar fallback state
73e1e6e docs: refresh handoff after training fallback guard
a697457 ui: guard training preflight fallback
1b950fe ui: guard montage preflight fallback
635f5b4 docs: refresh handoff after replay geometry gate
826cd96 test: gate interpretation replay geometry
f9819e4 docs: refresh handoff after clear availability guard
0e2c125 ui: guard dataset clear availability fallback
e61f1fd docs: refresh handoff after deterministic gate
261c732 eval: gate deterministic cli runs
4e8fe12 docs: refresh handoff after visible text guard
8862d14 test: guard walkthrough internal command text
70adaf1 docs: refresh handoff after training observer route
5c390da ui: route live training updates
4d58ff5 docs: refresh handoff after chat evidence
cd1a94b test: capture chat bubble visible text
8f60a6c docs: refresh handoff after selector fit
2a711d4 ui: fit interpretation label selectors
2f5ccb0 ui: gate dataset clear action
48af56d ui: deduplicate aggregate info refresh
6e99b03 ui: surface eval claim boundary
ca469ff ui: render eval dashboard artifact
83b0015 test: guard stale render fallbacks
e79d3b6 ui: guard dataset render fallback
41930e0 ui: show montage fallback warning
c26cb99 ui: show inline metadata fallback warning
789b520 docs: refresh handoff after preprocess warnings
fc14dd3 ui: show preprocess fallback warnings
f03f8d4 docs: refresh handoff after direct load warning
3d1321a ui: show direct load fallback warning
28e4e27 docs: refresh handoff after smart parse filename warning
724447b ui: show smart parse filename fallback warning
ba2c714 docs: refresh handoff after label import warning
6f06503 ui: show label import fallback warning
8fca05e docs: refresh handoff after smart parse warning
eed6066 ui: show smart parse fallback warning
09c3d40 docs: refresh handoff after metadata warning
e5d1e20 ui: show metadata fallback warning
40d3e22 docs: refresh handoff after remove files warning
be0f188 ui: show remove files fallback warning
e8e65bc ui: block missing data splitting context
5851718 docs: refresh handoff after start training warning
5ad6b7d ui: show start training fallback warning
c54b88c docs: refresh handoff after training settings warning
9abb334 ui: show training settings fallback warning
f2e5517 docs: refresh handoff after model selection warning
78c53d1 ui: show model selection fallback warning
65d23cc docs: refresh handoff after data splitting clear warning
cdab73f ui: show data splitting clear fallback warning
2394e13 docs: refresh handoff after dataset generation warning
c93012d ui: show dataset generation fallback warning
b3424d0 docs: refresh handoff after channel selection warning
ea16c8b ui: show channel selection fallback warning
2489ed1 docs: refresh handoff after dataset clear warning
dc3c486 ui: show dataset clear fallback warning
a6f140e docs: refresh handoff after preprocess reset warning
6f6ca72 ui: show preprocess reset fallback warning
088cb5c docs: refresh handoff after clear history warning
9c81f4d ui: show clear history fallback warning
0679cec docs: refresh handoff after stop training warning
85b4200 ui: show stop training fallback warning
23e196d docs: refresh handoff after visualization average guard
7fc1027 ui: guard visualization average fallback
ad0ba84 docs: refresh handoff after evaluation selection guard
c7d13ca ui: guard evaluation stale selection fallback
ca6556d docs: refresh handoff after training history guard
bdfebfa ui: guard training history fallback
8f0299d docs: refresh handoff after visualization query guard
18f2c87 ui: guard visualization query fallback
55bb2e5 docs: refresh handoff after evaluation query guard
fdea34a ui: guard evaluation query fallback
4cfa4c3 docs: refresh handoff after visualization fallback warnings
3330f1d ui: show visualization fallback refusals
8034739 docs: refresh handoff after preprocess render guard
a86b1b2 ui: guard preprocess render query fallback
1fd080a docs: refresh handoff after dialog fallback guard
a315170 ui: guard dialog query fallback paths
1ade9d2 docs: refresh handoff after label target fallback
b6b6d00 ui: block stale label target fallback
1e59b29 docs: refresh handoff after split dialog boundary
2a08679 ui: require split dialog service context
4ff4c43 docs: refresh handoff after visualization query fallback
fe978ce ui: keep visualization failed query authoritative
2c62662 docs: refresh handoff after preprocess query slice
d786276 ui: query preprocess plot data through service
aea3d3a docs: refresh handoff after walkthrough geometry gate
865b7c6 ui: flag clipped rows in walkthrough artifacts
61312fc ui: route training updates through refresh coordinator
1067c18 ui: prevent clipped interpretation review rows
f4a4bfb eval: require explicit release gate for full local runs
3ecb698 ui: release metrics chart canvas on close
62b7f64 ui: clean up confusion matrix canvas
5ab35ba ui: release saliency canvases on replace
f9acb77 ui: release plot window figures on close
28c144a ui: ignore stale preprocess psd results
d8221bb ui: source rereference dialog from state query
9a5d0ef ui: clean up 3d visualization widgets
5ff0790 training: bound force cleanup waits
5940b7d llm: release local runtime on shutdown
cc1b03e docs: refresh handoff after downloader lifecycle cleanup
435d9a9 llm: clean up model downloader lifecycle
51a6149 ui: clean up split preview worker
9816f85 docs: refresh handoff after split context query
4ddfa92 ui: source split dialog context from service
c21d7eb ui: export saliency from service trainers
338a763 docs: refresh handoff after training history query
e067e73 ui: render training history from state query
f2ccf95 ui: render visualization from service payload
a00a5d5 ui: render evaluation from service payload
c6c7e5b ui: query channel selection data
0cea91e docs: refresh handoff after label target cleanup
4f96005 ui: select label targets from dataset table
876c154 docs: refresh handoff after dataset render query
3f63592 ui: render dataset table from state query
3766764 docs: refresh handoff after aggregate info query
272dc5e ui: keep aggregate info on query truth
5e9e351 docs: refresh handoff after preprocess render query
feb9f88 ui: render preprocess panel from state query
29137da docs: refresh handoff after preprocess query guard
ebbdcfd ui: query epoching data through command spine
bb005ab ui: render preprocess sidebar from capabilities
7ab9501 ui: load training settings from state snapshot
7978c54 docs: refresh handoff after query-truth slices
d0a66b2 ui: use state query for smart parse files
d2e5b73 ui: use state query for montage channels
7b3c3e7 ui: use command query for saliency settings
f0ce929 docs: clarify local eval gate policy
c370929 docs: refresh handoff after saliency export gate
9327a4d ui: gate saliency export with query result
af9048f docs: refresh handoff after visualization query gate
25022fe ui: gate visualization display with query result
f845829 docs: refresh handoff after evaluation query gate
699e829 ui: gate evaluation display with query result
c4dc092 docs: refresh handoff after dataset sidebar audit
0c3de01 ui: render dataset sidebar from capabilities
b0b7b09 docs: refresh handoff after readiness echo guard
e309996 test: guard training readiness controller echoes
a6a6ba1 docs: refresh handoff after epoch gate audit
a7b7222 ui: gate epoching with create capability
343f8f9 docs: refresh handoff after readiness guard
d5388e7 test: guard capability-gated controller readiness
57b5d9c docs: refresh handoff after train gate audit
82576f5 ui: prefer train capability over stale controller
7a59e39 docs: refresh handoff after split audit
bb57beb ui: use backend truth for split replacement
```

## What Was Closed In This Slice

- Dataset action handler no-capability preflight fallback boundary:
  - `DatasetActionHandler.import_data()`, `_can_start_interpretation()`, and
    `open_smart_parser()` no longer directly read `DatasetController.is_locked()` / `has_data()`
    when command capability lookup is unexpectedly unavailable.
  - File import preserves the existing service-backed `LoadDataCommand` compatibility path while
    avoiding stale lock reads; folder/BIDS and Smart Parse use explicit legacy fallback boundaries.
  - Static scan now has no matches for
    `capability is None and self.controller...` / `capability is None and controller...` in
    `XBrainLab/ui`.
  - Validation covered red stale-controller tests, Dataset action regression, full fast gate
    (`git diff --check`, ruff, basedpyright, architecture compliance, mkdocs strict, backend
    integration, and agent/tool deterministic regression).
  - No local LLM eval was run; this was a UI fallback audit slice under the fast dev gate.
- Preprocess sidebar no-capability lock/data fallback boundary:
  - `PreprocessSidebar.check_lock()` and `check_data_loaded()` now route no-capability fallback
    reads through `run_legacy_controller_fallback()` via `_run_legacy_preprocess_fallback()`.
  - Real `Study` no longer reads stale `PreprocessController.is_epoched()` / `has_data()` when
    `preprocess` capability lookup is unexpectedly unavailable; mock / legacy contexts keep
    controller compatibility behavior.
  - Validation covered red stale-controller tests, Preprocess sidebar regression, full fast gate
    (`git diff --check`, ruff, basedpyright, architecture compliance, mkdocs strict, backend
    integration, and agent/tool deterministic regression).
  - No local LLM eval was run; this was a UI fallback audit slice under the fast dev gate.
- Dataset sidebar no-capability lock/data fallback boundary:
  - `DatasetSidebar.update_sidebar()` now routes no-capability lock/data reads through
    `run_legacy_controller_fallback()` instead of directly reading stale
    `DatasetController.is_locked()` / `has_data()`.
  - Source / folder-BIDS / recipe / channel / smart-parse / label buttons show unavailable state
    in real `Study` contexts when command capability lookup is unexpectedly unavailable; mock /
    legacy contexts keep controller compatibility behavior.
  - `open_channel_selection()` now shows `Channel Selection Blocked` instead of reading stale
    loaded-data / lock state in real `Study` no-capability fallback.
  - Validation covered red stale-controller tests, Dataset sidebar regression, full fast gate
    (`git diff --check`, ruff, basedpyright, architecture compliance, mkdocs strict, backend
    integration, and agent/tool deterministic regression).
  - No local LLM eval was run; this was a UI fallback audit slice under the fast dev gate.
- Training sidebar no-capability preflight fallback boundary:
  - `TrainingSidebar` now routes no-capability fallback reads through
    `run_legacy_controller_fallback()` instead of directly reading stale
    `TrainingController` state.
  - Covered paths: `check_ready_to_train()` readiness / tooltip, Data Splitting loaded-data /
    epoch / running preflight, model/settings configuration lock checks, Stop Training preflight,
    and Clear History preflight.
  - Real `Study` contexts now disable Start Training with state-unavailable tooltip or show
    product blocked warnings; mock / legacy contexts keep controller compatibility behavior.
  - Validation covered red stale-controller tests, `TestTrainingSidebar` regression, full fast gate
    (`git diff --check`, ruff, basedpyright, architecture compliance, mkdocs strict, backend
    integration, and agent/tool deterministic regression).
  - No local LLM eval was run; this was a UI fallback audit slice under the fast dev gate.
- Montage preflight fallback boundary:
  - `ControlSidebar.set_montage()` no longer reads stale
    `VisualizationController.has_epoch_data()` when `apply_montage` capability lookup unexpectedly
    returns `None` in a real `Study` runtime.
  - Mock / legacy contexts still use `run_legacy_controller_fallback()` and retain the existing
    controller compatibility path.
  - Validation covered the red stale-controller read, focused montage behavior, Visualization
    sidebar regression, full fast gates, backend integration, and agent/tool regression.
  - No local LLM eval was run; this was a UI fallback audit slice.
- Data Interpretation replay geometry gate:
  - `scripts/dev/capture_data_interpretation_replay.py` now writes
    `ui_quality_review.geometry` into `artifacts/ui/data-interpretation-replay.json`.
  - The standalone replay now fails if captured preview/remap wizard tables or the loaded Dataset
    table show horizontal overflow, viewport underfill, content-boundary gaps, or clipped visible
    rows.
  - Latest replay artifact reports `passed=true`, `checked_widgets=9`, and `findings=[]`.
  - Preview/remap screenshots were spot-reviewed after refresh; tables are nonblank and fill the
    panel under the synthetic replay geometry.
  - No local LLM eval was run; this was UI-observable replay evidence under the fast dev gate.
- Dataset Clear availability fallback boundary:
  - `_clear_dataset_availability()` no longer reads `DatasetController.has_data()` directly when
    `QueryStateCommand(query="state")` unexpectedly returns `None`.
  - Mock / legacy contexts still use `run_legacy_controller_fallback()`, while real `Study`
    contexts disable `Clear Dataset` with `Dataset state is unavailable right now.`.
  - The existing real-Study reset-command fallback test now separates the availability query from
    the reset command, so it still proves the reset fallback warning path without relying on stale
    controller state for button availability.
  - No local LLM eval was run; this was a UI fallback audit slice.
- Deterministic tool-call eval CLI gate:
  - `scripts/agent/evals/run_tool_call_eval.py` now defaults to `--eval-gate fast --repeat-count 1`.
  - Routine CLI runs must select a changed / affected subset with `--case-id`, `--case-family`, or
    `--case-limit`; a default full-suite fast run exits `2` and writes
    `deterministic_gate.json` / `.md` instead of refreshing `latest.json`.
  - Full-suite deterministic dashboard refresh now requires explicit `--eval-gate release` or
    `--eval-gate thesis`.
  - `run_eval()` keeps the Python API full-suite behavior for tests and scorer validation, but also
    accepts optional case filters for focused checks.
  - No local LLM eval was run; this slice changes runner policy only and does not update formal
    deterministic / primary / fallback benchmark claims.
- Walkthrough internal command leakage guard:
  - `forbidden_visible_text()` now flags selected internal command names beyond the original Data
    Interpretation set, including `configure_training`, `generate_dataset`, `create_epoch`,
    `query_state`, and legacy `load_data` / `attach_labels` / `import_labels`.
  - The consolidated human-like walkthrough was refreshed and still passes with `0` forbidden
    visible-text findings.
  - This is an automated UI-observable guard only; it does not replace human copy review or long
    local-model ChatPanel acceptance.
- Training updated observer handler routing:
  - `TrainingPanel` no longer wires `training_updated` to a lambda that only calls `update_loop()`.
  - A named `_on_training_updated()` keeps the live progress update and then calls
    `refresh_after_observer(self, event_name="training_updated")`.
  - This aligns the actual observer callback with the coordinator route that already maps
    `training_updated` to Training / Evaluation / Visualization, aggregate info, and assistant
    status refresh.
  - Updated `docs/architecture/ui.md` to remove the stale statement that high-frequency
    `training_updated` stays Training-panel-only.
- ChatPanel walkthrough visible-text evidence:
  - `visible_text_snapshot()` now includes `QTextBrowser.toPlainText()`, so ChatPanel bubble text is
    represented in JSON visible-text snapshots instead of only in screenshots.
  - `run_chatpanel_walkthrough()` captures `visible_messages`, send/input state, and processing
    state before `start_new_conversation()` clears the bubbles for the reset/new-session boundary.
  - Refreshed `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` and `.md`;
    assistant normal / clarification / blocked / success / narrow phases now include visible user
    and assistant bubble text.
  - `chatpanel.visible_messages` now records the eight visible user/assistant bubbles before reset.
  - This strengthens automated UI-observable evidence only; it is not human Windows desktop
    acceptance, true local-model long-session testing, or proof of every autonomous ChatPanel
    workflow.
- Data Interpretation selector-fit polish:
  - `DataInterpretationPreviewDialog` rebalanced the label carrier table columns so Time /
    Granularity `Needs review` selectors are no longer visibly clipped in product-width replay.
  - Matched EEG targets now display compact BIDS labels such as `sub-01 run-2`, keeping the run
    identifier visible in the table.
  - Full filenames remain preserved in `Qt.UserRole`, combo data, replay `review_choices`, and
    apply diagnostics; replay still applies labels to `sub-01_task-mi_run-2_raw.fif`.
  - `apply_replay_review_choices()` now selects target files by combo data instead of visible text.
  - Refreshed `artifacts/ui/data-interpretation-preview.png`,
    `artifacts/ui/data-interpretation-remap.png`, `data-interpretation-replay.json`, and the
    consolidated human-like walkthrough preview/confirm/reload screenshots.
- Dataset Clear empty-state boundary:
  - real `Study` `DatasetSidebar.update_sidebar()` now queries
    `QueryStateCommand(query="state")` before enabling `Clear Dataset`.
  - empty startup / reset state keeps `Clear Dataset` disabled with `No dataset to clear.`;
    Data Interpretation apply re-enables it.
  - direct empty `clear_dataset()` now shows a short notice instead of opening reset
    confirmation.
  - disabled success / danger / warning action colors now use neutral disabled tokens, so disabled
    destructive buttons no longer look active.
  - refreshed `artifacts/ui/human-like-walkthrough/02-dataset-page.png` and the walkthrough JSON /
    Markdown; JSON spot-check shows startup/reset disabled and apply enabled.
- MainWindow aggregate-info observer deduplication:
  - MainWindow now constructs `InfoPanelService(study, observe_controller_events=False)`.
  - Product runtime aggregate info refresh is owned by `refresh_coordinator` shared-status refresh
    calling `MainWindow.update_info_panel()` / `InfoPanelService.notify_all()`.
  - Standalone / legacy InfoPanelService usage keeps the default direct controller observer bridges.
- Human-like walkthrough eval dashboard presentation:
  - `scripts/dev/capture_human_like_product_walkthrough.py` now renders
    `artifacts/agent_evals/dashboard.md` as product-style HTML in a `QTextBrowser` instead of
    capturing raw Markdown / pipe-table text.
  - `artifacts/ui/human-like-walkthrough/20-eval-dashboard.png` now shows dark model-comparison
    and metric tables, matching the main product visual language better.
  - The same screenshot now surfaces the Thesis Claim Boundary before the benchmark tables, so the
    first viewport states that the score does not claim UI usability, Windows launcher coverage, or
    product completion.
  - This was a UI-observable artifact polish slice only; no deterministic or local LLM benchmark
    score changed.
- Stale render fallback architecture guard:
  - `tests/architecture_compliance.py` now flags direct controller render reads inside
    `result is None` branches unless they go through `run_legacy_controller_fallback()`.
  - Covered render methods include loaded/preprocessed data lists, training history, evaluation
    plans, visualization trainers, montage channel defaults, saliency params, and summary reads.
  - Current repo passes the new guard.
- DatasetPanel query-none render fallback boundary:
  - real `Study` Dataset table refresh now clears to an empty table when
    `QueryStateCommand(query="data_lists")` returns `None`.
  - the UI no longer reads stale `DatasetController.get_loaded_data_list()` in that unexpected
    service-unavailable render path.
  - mock / legacy non-`Study` render fallback still uses `DatasetController.get_loaded_data_list()`.
- AgentManager montage fallback warning:
  - real `Study` assistant montage confirmation now shows `Montage setup blocked` when
    `ApplyMontageCommand` returns `None`.
  - the UI no longer lets legacy fallback refusal escape from
    `AgentManager.open_montage_picker_dialog()` or call `PreprocessController.apply_montage()` in
    product runtime.
  - mock / legacy non-`Study` montage fallback still calls `PreprocessController.apply_montage()`.
- Dataset inline metadata fallback warning:
  - real `Study` inline subject/session edits now show `Metadata blocked` when
    `UpdateMetadataCommand` returns `None`.
  - the UI no longer lets legacy fallback refusal escape from `DatasetPanel.on_item_changed()`.
  - mock / legacy inline metadata fallback still calls `DatasetController.update_metadata()`.
- Preprocess operation fallback warning:
  - real `Study` filtering, resampling, re-reference, normalization, and epoching fallback refusal
    now shows operation-specific Blocked warnings.
  - the UI no longer tries controller mutation or wraps these refusals in generic failed text when
    preprocess commands return `None`.
  - the architecture guard now explicitly allows the named preprocess legacy wrapper while still
    flagging naked controller mutations in missing-result branches.
- Direct Load compatibility fallback warning:
  - real `Study` direct-load compatibility fallback refusal now shows `Interpretation Blocked`.
  - the UI no longer tries `DatasetController.import_files()` or wraps the refusal in generic import
    failure when direct `LoadDataCommand` returns `None`.
  - mock / legacy direct import fallback still calls `DatasetController.import_files()`.
- Smart Parse filename fallback warning:
  - real `Study` smart-parse filename-query fallback refusal now shows `Smart Parse Blocked`.
  - the UI no longer reads stale `DatasetController.get_filenames()` when
    `QueryStateCommand(query="state")` returns `None`.
  - mock / legacy filename fallback still calls `DatasetController.get_filenames()`.
- Label Import fallback warning:
  - real `Study` label-import apply fallback refusal now shows `Label Import Blocked`.
  - the UI no longer wraps the legacy fallback refusal in generic `Failed: ...` critical text when
    `ImportLabelsCommand` returns `None`.
  - mock / legacy label import fallback still calls `DatasetController.apply_labels_legacy()` /
    `apply_labels_batch()`.
- Smart Parse apply fallback warning:
  - real `Study` smart-parse apply fallback refusal now shows `Smart Parse Blocked`.
  - the UI no longer lets the legacy fallback exception escape when `ApplySmartParseCommand`
    returns `None`.
  - mock / legacy smart-parse fallback still calls `DatasetController.apply_smart_parse()`.
- Metadata Update fallback warning:
  - real `Study` inline/context-menu metadata-update fallback refusal now shows
    `Metadata Update Blocked`.
  - the UI no longer lets the legacy fallback exception escape when `UpdateMetadataCommand`
    returns `None`.
  - mock / legacy metadata fallback still calls `DatasetController.update_metadata()`.
- Remove Files fallback warning:
  - real `Study` remove-files fallback refusal now shows `Remove Files Blocked`.
  - the UI no longer lets the legacy fallback exception escape when `RemoveFilesCommand` returns
    `None`.
  - mock / legacy remove-files fallback still calls `DatasetController.remove_files()`.
- Data Splitting context query-none boundary:
  - real `Study` dataset-generation context query-none now shows `Data Splitting Blocked`.
  - the UI no longer opens `DataSplittingDialog` without service-backed epoch/generator context.
  - mock / legacy contexts retain the old empty-context dialog behavior.
- Start Training fallback warning:
  - real `Study` start-training fallback refusal now shows `Start Training Blocked`.
  - the UI no longer wraps the safe refusal in a generic critical training failure when
    `TrainCommand` returns `None`.
  - mock / legacy start fallback still calls `TrainingController.start_training()`.
- Training Settings fallback warning:
  - real `Study` training-settings fallback refusal now shows `Training Settings Blocked`.
  - the UI no longer lets the legacy fallback exception escape when the option-side
    `ConfigureTrainingCommand` returns `None`.
  - mock / legacy training-settings fallback still calls
    `TrainingController.set_training_option()`.
- Model Selection fallback warning:
  - real `Study` model-selection fallback refusal now shows `Model Selection Blocked`.
  - the UI no longer lets the legacy fallback exception escape when the model-side
    `ConfigureTrainingCommand` returns `None`.
  - mock / legacy model-selection fallback still calls `TrainingController.set_model_holder()`.
- Data Splitting clear fallback warning:
  - real `Study` clear-datasets preflight fallback refusal now shows `Data Splitting Blocked`.
  - the UI no longer lets the legacy fallback exception escape when
    `ClearDatasetsCommand` returns `None`.
  - mock / legacy data-splitting cleanup fallback still calls
    `TrainingController.clean_datasets(force_update=True)`.
- Generate Dataset apply fallback warning:
  - real `Study` dataset-generation apply fallback refusal now shows `Data Splitting Blocked`.
  - the UI no longer lets the legacy fallback exception escape when
    `GenerateDatasetCommand` returns `None`.
  - mock / legacy data-splitting fallback still calls
    `TrainingController.apply_data_splitting()`.
- Channel Selection apply fallback warning:
  - real `Study` channel-selection apply fallback refusal now shows `Channel Selection Blocked`.
  - the UI no longer wraps the safe refusal in a generic critical channel-selection failure.
  - mock / legacy channel-selection fallback still calls
    `DatasetController.apply_channel_selection()`.
- Dataset Clear fallback warning:
  - real `Study` clear-dataset fallback refusal now shows `Clear Dataset Blocked`.
  - the UI no longer wraps the safe refusal in a generic critical clear-dataset failure.
  - mock / legacy clear fallback still calls `DatasetController.clean_dataset()`.
- Preprocess Reset fallback warning:
  - real `Study` reset-preprocess fallback refusal now shows `Reset Blocked`.
  - the UI no longer wraps the safe refusal in a generic critical reset failure.
  - mock / legacy reset fallback still calls `PreprocessController.reset_preprocess()`.
- Clear History fallback warning:
  - real `Study` clear-history fallback refusal now shows `Clear History Blocked`.
  - the UI no longer wraps the refusal in generic `Warning` / `Error clearing history: ...` text.
  - mock / legacy clear-history fallback still calls `TrainingController.clear_history()`.
- Stop Training fallback warning:
  - real `Study` stop-training fallback refusal now shows `Stop Training Blocked`.
  - the UI no longer lets `LegacyControllerFallbackUnavailableError` escape as a raw runtime error.
  - mock / legacy stop fallback still calls `TrainingController.stop_training()`.
- Visualization average stale-selection fallback:
  - real `Study` stale Average selections without a service payload no longer recover through
    `VisualizationController.get_averaged_record()`.
  - the panel shows the existing user-facing `No finished runs to average.` message instead of
    reading stale controller data.
  - mock / legacy rendering still uses explicit `run_legacy_controller_fallback()`.
- Evaluation stale-selection fallback:
  - `EvaluationPanel` now initializes its service-query state.
  - real `Study` stale average/summary selections without a service payload no longer recover
    through `EvaluationController.get_pooled_eval_result()` /
    `get_model_summary_str()`.
  - mock / legacy rendering still uses explicit `run_legacy_controller_fallback()`.
- Training history query-none render fallback:
  - real `Study` Training panel now treats a missing
    `QueryStateCommand(query="training_history", include_objects=True)` result as unavailable
    command truth.
  - it clears to an empty training display instead of recovering through stale
    `TrainingController.get_formatted_history()`.
  - mock / legacy rendering still uses explicit `run_legacy_controller_fallback()`.
- Visualization query-none render fallback:
  - real `Study` Visualization panel now treats a missing
    `VisualizeCommand(include_objects=True)` result as unavailable command truth.
  - it keeps empty plan/run controls instead of recovering through stale
    `VisualizationController.get_trainers()` / averaged records.
  - mock / legacy rendering still uses explicit `run_legacy_controller_fallback()`.
- Evaluation query-none render fallback:
  - real `Study` Evaluation panel now treats a missing
    `EvaluateCommand(include_objects=True)` result as unavailable command truth.
  - it renders `No Data Available` instead of recovering through stale
    `EvaluationController.get_plans()` / summaries.
  - mock / legacy rendering still uses explicit `run_legacy_controller_fallback()`.
- Data Interpretation wizard selector visible text:
  - label carrier selectors show user-facing labels such as `Trial type` / `Onset`.
  - backend recipe choices still preserve raw values such as `trial_type`.
- Review Summary contrast:
  - alternate row color lowered to `#232323`, avoiding harsh black/white striping.
  - latest polish fixes clipped Review Summary rows; `tree_state()` records
    `vertical_scrollbar_max` and `partial_visible_rows`, and the refreshed replay shows
    `partial_visible_rows=[]` for preview and remap dialogs.
  - consolidated human-like walkthrough quality review now fails on any captured
    `partial_visible_rows` for table/tree widgets; latest artifact checks `15` widgets with
    `0` geometry findings and `0` clipped-row findings.
- Label/Event review table readability:
  - label-carrier `Format` column widened so `BIDS events` remains visible in product-width dialog.
- Dataset loaded table artifact:
  - `artifacts/ui/data-interpretation-applied.png` shows loaded rows filling to the sidebar.
  - `Labels (4)` is muted text, not success-green.
- Automated geometry guard:
  - `table_state()` now records `widget_width`, `panel_width`, `table_right_x`,
    `right_boundary_x`, `right_gap_to_boundary`, `vertical_scrollbar_max`, and
    `partial_visible_rows`.
  - `build_table_geometry_review()` now fails if a table fills only its own viewport but leaves a
    visible gap before the content boundary, or if a captured table/tree widget shows a
    half-visible row at the viewport edge.
  - Latest `artifacts/ui/data-interpretation-replay.json` records
    `widget_width=1020`, `table_right_x=1020`, `right_boundary_x=1020`,
    `right_gap_to_boundary=0` for the 1280px loaded Dataset capture.
- Preprocess plotter render source:
  - `PreprocessPanel` and `PreprocessPlotter` now share `query_preprocess_render_lists()`.
  - Direct `plot_sample_data()` calls use `QueryStateCommand(query="data_lists",
    include_objects=True)` before controller reads.
  - Controller data-list reads remain only for query-unavailable mock / legacy fallback.
- Visualization failed-query trainer fallback:
  - `VisualizationPanel.get_trainers()` now returns `[]` when an ApplicationService visualization
    query has failed.
  - Stale `VisualizationController.get_trainers()` fallback remains only when no ApplicationService
    query exists for mock / legacy panel compatibility.
- Data Splitting dialog context boundary:
  - real `Study` `DataSplittingDialog` no longer reads `TrainingController.get_epoch_data()` /
    `get_dataset_generator()` when explicit service-backed context is missing.
  - Training sidebar continues to pass `dataset_generation_context`; controller fallback remains
    only for mock / legacy dialog construction.
- Visualization sidebar `Set Montage` missing-result handling:
  - no longer silently returns when `execute_application_command()` unexpectedly returns `None`.
  - mock / legacy contexts use `run_legacy_controller_fallback()`; real `Study` contexts refuse
    controller fallback.
- Dataset file import boundary:
  - if `scan_source` capability exists but Data Interpretation command sequencing is unavailable,
    the UI shows `Interpretation unavailable`.
  - it does not fall through to `LoadDataCommand` or `DatasetController.import_files()`.
- Training model selection command truth:
  - service-success path now trusts `ConfigureTrainingCommand` and the selected model holder.
  - it no longer re-reads stale `TrainingController.get_model_holder()` before showing success.
  - architecture compliance now guards this controller echo pattern.
- Training split replacement command truth:
  - real `Study` path uses backend `generate_dataset` / `clear_datasets` capability truth to decide
    whether existing generated datasets / trainer must be cleared before a new split.
  - stale `TrainingController.has_datasets()` / `get_trainer()` no longer skips confirmation and
    `ClearDatasetsCommand`.
- Start Training command truth:
  - real command-capable path uses backend `train` capability truth to decide whether to dispatch
    `TrainCommand`.
  - stale `TrainingController.is_training()` no longer silently skips an enabled backend train
    command.
- Capability-gated readiness architecture guard:
  - `tests/architecture_compliance.py` now flags `controller.is_training()`,
    `controller.has_datasets()`, and `controller.get_trainer()` in command paths that already have
    backend capability truth.
  - Such reads must live in explicit `capability is None` legacy branches.
- Training readiness controller echo guard:
  - The same architecture guard now covers `validate_ready()`, `has_model()`, and
    `has_training_option()` controller reads.
  - `TrainingSidebar.check_ready_to_train()` uses an explicit service-capability branch versus
    no-capability legacy branch.
- Dataset sidebar capability-first render:
  - The architecture guard now also covers `DatasetController.is_locked()` and `has_data()` reads
    in capability-backed UI paths.
  - `DatasetSidebar.update_sidebar()` no longer reads stale lock/data controller state when backend
    command capabilities are present.
  - Those controller reads remain only in explicit no-capability legacy branches.
- Evaluation panel query display gate:
  - A real `Study` Evaluation panel now uses the readonly `EvaluateCommand` result as the display
    gate.
  - If ApplicationService reports evaluation blocked or unavailable, the panel clears to
    `No Data Available` instead of reading stale injected controller plans.
- Evaluation panel object-payload render source:
  - `EvaluateCommand(include_objects=True)` now returns UI-only plan objects, pooled evaluation
    results, and model summaries for service-backed rendering.
  - A real `Study` Evaluation panel uses that service payload for plan list, average metrics, and
    summary text before falling back to controller reads.
  - Automation / MCP `evaluate` schemas hide and reject `include_objects`, keeping external
    clients on the serializable query contract.
  - `.basedpyright/baseline.json` dropped by 3 suppressed optional-controller errors.
- Visualization panel query display gate:
  - A real `Study` Visualization panel now uses readonly `VisualizeCommand` results as the
    controls/render gate.
  - If ApplicationService reports visualization blocked or unavailable, the panel clears plan/run
    controls and shows a user-facing readiness message before reading injected controller trainers.
  - The basedpyright baseline dropped from 115 to 112 suppressed errors after replacing dynamic
    `show_error` calls with a typed helper.
- Visualization panel object-payload render source:
  - `VisualizeCommand(include_objects=True)` now returns UI-only trainer objects and averaged
    records for service-backed rendering.
  - A real `Study` Visualization panel uses that service payload for plan controls and average-run
    rendering before falling back to controller reads.
  - Automation / MCP `visualize` schemas hide and reject `include_objects`, keeping external
    clients on the serializable query contract.
  - `.basedpyright/baseline.json` dropped by 2 more suppressed errors.
- Saliency export query gate:
  - `Export Saliency` now checks readonly `SaliencyCommand` readiness before reading trainer lists
    or opening the export dialog.
  - If saliency output is unavailable, the sidebar shows `Export Saliency Blocked`.
- Saliency settings query defaults:
  - `Saliency Settings` now checks readonly `SaliencyCommand` summary diagnostics before opening
    the settings dialog.
  - `VisualizationController.get_saliency_params()` is only used through the mock / legacy query
    fallback helper when ApplicationService query result is unavailable.
- Montage channel query defaults:
  - `Set Montage` now checks `QueryStateCommand(query="state")` for `state.epoch.channel_names`
    before opening the montage picker.
  - `VisualizationController.get_channel_names()` is only used through the mock / legacy query
    fallback helper when ApplicationService query result is unavailable.
  - latest fallback language slice catches real `Study` query-none and apply-none fallback refusal
    and shows a product warning instead of letting `LegacyControllerFallbackUnavailableError`
    escape from the Qt slot.
- Dataset smart-parse query defaults:
  - `Smart Parse Metadata` now checks `QueryStateCommand(query="state")` for `state.raw.files`
    before opening the parser dialog.
  - `DatasetController.get_filenames()` is only used through the mock / legacy query fallback
    helper when ApplicationService query result is unavailable.
- Training settings state snapshot defaults:
  - `Training Settings` now checks `QueryStateCommand(query="state")` for
    `state.training.training_option` before opening the settings dialog.
  - `TrainingController.get_training_option()` is only used in mock / legacy query fallback.
- Training history query render source:
  - `QueryStateCommand(query="training_history", include_objects=True)` now returns service-backed
    training history rows for table rendering and plot selection.
  - A real `Study` Training panel uses that payload before falling back to
    `TrainingController.get_formatted_history()`.
  - The query returns serializable row summaries by default and plan/record objects only for
    `include_objects=True`.
- Visualization export trainer render source:
  - `Export Saliency` still uses readonly `SaliencyCommand` as the export readiness gate.
  - When export is ready, it now opens the export dialog from
    `VisualizeCommand(view="summary", include_objects=True)` `trainer_objects`.
  - `panel.get_trainers()` / `VisualizationController.get_trainers()` remain only for
    query-unavailable mock / legacy fallback.
  - latest fallback language slice catches query-none legacy fallback refusal and shows
    `Export Saliency Blocked` with the shared safety message.
- Training split dialog context query:
  - `QueryStateCommand(query="dataset_generation_context", include_objects=True)` now returns the
    epoch data and current dataset generator needed by `DataSplittingDialog`.
  - A real `Study` Training sidebar passes that service-backed context into the dialog.
  - `TrainingController.get_epoch_data()` / `get_dataset_generator()` remain only for
    query-unavailable mock / legacy dialog fallback.
- Data Splitting preview worker cleanup:
  - `DataSplittingPreviewDialog.preview()` interrupts and short-joins the previous preview worker
    before starting a new `DatasetGenerator`.
  - `DataSplittingPreviewDialog.closeEvent()` stops the timer, interrupts the generator, and
    short-joins the worker before Qt close handling.
  - This is focused lifecycle coverage, not a long-running dataset-generation soak test.
- Local model downloader lifecycle cleanup:
  - `DownloadWorker.run()` now reaps the subprocess after terminal queue messages and closes the
    multiprocessing queue after the worker loop exits.
  - cancel uses bounded terminate / kill joins instead of an unbounded process join.
  - `ModelDownloader.shutdown()` cancels the worker, requests `QThread.quit()`, then bounded-waits
    for thread cleanup.
  - `ModelSettingsDialog.reject()` / `closeEvent()` now use that shutdown path while suppressing
    teardown cleanup popups.
  - This is focused lifecycle coverage, not a long-running local model soak or Windows desktop
    acceptance.
- Local runtime shutdown cleanup:
  - `LocalBackend.unload()` releases model / tokenizer references, runs garbage collection, and
    clears CUDA cache when CUDA is available.
  - `LLMEngine.close()` unloads cached local backends and clears active backend references; stale
    backend reloads now unload the old backend before replacement.
  - `AgentWorker.shutdown()` stops timeout timers, interrupts / bounded-waits generation threads,
    keeps running generation threads alive until Qt emits finished, and closes the engine.
  - `LLMController.close()` calls worker shutdown before bounded-waiting the worker thread.
  - This is assistant lifecycle resource cleanup, not a long-running true local model UI soak or
    GPU leak-proof acceptance.
- Training force-clean thread handle guard:
  - `Trainer.clean(force_update=True)` now sets interrupt and bounded-joins the background
    training thread when called from outside the job thread.
  - if the training thread is still alive after the timeout, cleanup raises and leaves the trainer
    handle intact so later cancel/status paths are still reachable.
  - `TrainingManager.clean_trainer()` only clears the trainer after `trainer.clean()` succeeds.
  - This is thread-handle safety coverage, not a long-running training soak.
- Visualization 3D widget cleanup:
  - `Saliency3DPlotWidget.clear_plot()` now detaches plot-layout children, schedules non-plotter
    child widgets for `deleteLater()`, and closes / deletes the PyVista plotter with runtime-safe
    method checks before clearing the reference.
  - This is focused 3D widget lifecycle coverage, not interactive desktop 3D / PyVista render
    acceptance or an OpenGL soak.
- Preprocess re-reference dialog query source:
  - command-capable `open_rereference()` now gets dialog data through
    `QueryStateCommand(query="data_lists", include_objects=True)`.
  - stale `PreprocessController.get_preprocessed_data_list()` remains only for no-capability
    mock / legacy dialog population.
  - This continues the controller-read audit; it does not finish the full Preprocess UI workflow.
- Preprocess PSD stale-result guard:
  - async PSD worker results now carry a plot generation and are ignored if a newer
    `plot_sample_data()` call has started.
  - This prevents old PSD results from overwriting the latest frequency plot during rapid preview
    refresh, but it does not cancel running workers or prove long-run performance.
- Plot window close cleanup:
  - `SinglePlotWindow.closeEvent()` now closes the currently embedded Matplotlib figure, detaches
    canvas / toolbar widgets, schedules `deleteLater()`, and clears references.
  - This covers the base plot dialog used by training / evaluation / visualization plot windows,
    but it is not long-run visualization memory trend evidence.
- Saliency 2D canvas cleanup:
  - Map / Spectrogram / Topomap now share `BaseSaliencyView._replace_figure()` for figure
    replacement.
  - replacement and close paths close the current Matplotlib figure, detach the canvas, schedule
    `deleteLater()`, and clear references.
  - This is focused canvas lifecycle coverage, not full saliency UX or long-run visualization
    memory trend evidence.
- Confusion matrix canvas cleanup:
  - `ConfusionMatrixWidget.update_plot()` and close now close the current figure, detach /
    `deleteLater()` existing canvas or message widgets, and clear references before drawing new
    content.
  - This is focused Evaluation tab widget cleanup, not full evaluation UI soak evidence.
- Metrics chart close cleanup:
  - `MetricsBarChartWidget.closeEvent()` now closes the current Matplotlib figure, detaches /
    `deleteLater()` the canvas, and clears figure / canvas / axes references.
  - This covers the Evaluation tab per-class metrics chart close path, not long-run Evaluation
    memory trend proof.
- Preprocess epoch command truth:
  - `open_epoching()` uses backend `create_epoch` capability as the authoritative UI gate.
  - An enabled `create_epoch` capability is no longer vetoed by the separate `preprocess`
    capability through `check_lock()` / `check_data_loaded()`.
  - Legacy controller lock/data checks remain only for no-capability mock / legacy contexts.
- Preprocess sidebar capability-first render:
  - `update_sidebar()` no longer reads stale `PreprocessController.get_preprocessed_data_list()`
    when `preprocess` / `create_epoch` capabilities are visible.
  - The architecture guard now flags `get_preprocessed_data_list()` in capability-backed UI paths.
- Epoching dialog query data source:
  - command-capable `open_epoching()` now gets preprocessed dialog data through
    `QueryStateCommand(query="data_lists", include_objects=True)`.
  - `PreprocessController.get_preprocessed_data_list()` remains only for no-capability mock /
    legacy dialog population.
  - if a real `Study` path unexpectedly receives no query result, the dialog source fallback now
    blocks with the shared safety message instead of reading a stale controller list.
- Preprocess panel state-query render:
  - `PreprocessPanel.update_panel()` and `update_plot_only()` now query
    `QueryStateCommand(query="data_lists", include_objects=True)` in real `Study` contexts.
  - The panel passes queried preprocessed / original objects into `PreprocessPlotter`, so history,
    preview controls, and plot refresh do not start from stale controller list reads.
  - `PreviewWidget.request_plot_update` routes through `PreprocessPanel.update_plot_only()` to keep
    user control changes on the same query-backed render source.
  - `.basedpyright/baseline.json` dropped by one suppressed error after touched Preprocess tests
    and panel typing were cleaned up.
  - latest render fallback slice also guards query-none fallback: real `Study` panel refresh /
    direct plotter calls render no data / skip plotting instead of reading stale
    `PreprocessController.get_preprocessed_data_list()`.
- Aggregate info query-failure boundary:
  - real `Study` `InfoPanelService` keeps aggregate info on
    `QueryStateCommand(query="data_lists", include_objects=True)`.
  - if that query fails or raises, the service logs and returns an empty summary instead of falling
    back to dataset / preprocess controller list reads.
  - mock / legacy non-`Study` contexts keep the controller-list compatibility fallback.
- Dataset table state-query render:
  - real `Study` `DatasetPanel.update_panel()` uses
    `QueryStateCommand(query="data_lists", include_objects=True)` for loaded table rows.
  - `DatasetController.get_loaded_data_list()` remains only for no-ApplicationService mock /
    legacy rendering.
  - `.basedpyright/baseline.json` dropped by one more suppressed error after touched Dataset panel
    typing was cleaned up.
- Label import target selection:
  - post-load `Add Labels to Loaded Data` now resolves selected/all-row targets from the Dataset
    table's column-0 `Qt.UserRole` object before opening `ImportLabelDialog`.
  - `DatasetController.get_loaded_data_list()` remains only as a mock / legacy fallback when table
    row objects are unavailable.
  - latest boundary slice blocks real `Study` post-load label import if selected rows lack
    `UserRole` target data, instead of recovering from stale
    `DatasetController.get_loaded_data_list()`.
- Channel Selection dialog query source:
  - real command-capable `DatasetSidebar.open_channel_selection()` now queries
    `QueryStateCommand(query="data_lists", include_objects=True)` before opening
    `ChannelSelectionDialog`.
  - `DatasetController.get_loaded_data_list()` remains only for no-capability mock / legacy dialog
    population.
  - if a real `Study` path unexpectedly receives no query result, Channel Selection now blocks
    instead of opening a stale/empty controller-backed dialog.

## Validation Already Run

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_refuses_real_study_controller_fallback -q
# red first for 1b950fe; failed on stale controller.has_epoch_data() read

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_refuses_real_study_controller_fallback \
  tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_legacy_result_uses_controller_fallback \
  tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage -q
# 3 passed for 1b950fe

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py -q
# 28 passed

poetry run ruff check \
  XBrainLab/ui/panels/visualization/control_sidebar.py \
  tests/unit/ui/visualization/test_control_sidebar.py
poetry run basedpyright \
  XBrainLab/ui/panels/visualization/control_sidebar.py \
  tests/unit/ui/visualization/test_control_sidebar.py
# passed for 1b950fe; basedpyright reported 0 errors, 0 warnings, 0 notes

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 1b950fe; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_data_interpretation_replay.py::test_replay_geometry_review_flags_underfilled_tree -q
# red first for 826cd96; failed because build_replay_geometry_review did not exist

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_data_interpretation_replay.py -q
# 7 passed for 826cd96

poetry run ruff check \
  scripts/dev/capture_data_interpretation_replay.py \
  tests/unit/scripts/test_capture_data_interpretation_replay.py
poetry run basedpyright \
  scripts/dev/capture_data_interpretation_replay.py \
  tests/unit/scripts/test_capture_data_interpretation_replay.py
# passed for 826cd96; basedpyright reported 0 errors, 0 warnings, 0 notes

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py
# exit 0 for 826cd96; refreshed data-interpretation preview/remap/applied screenshots and replay JSON
# replay JSON ui_quality_review.geometry: passed true, checked_widgets 9, findings []

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 826cd96; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_data_interpretation_replay.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/integration/ui/test_product_walkthrough.py -q
# 29 passed

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_dataset_sidebar.py::test_update_sidebar_refuses_real_study_clear_availability_fallback -q
# red first for 0e2c125; failed on stale controller.has_data() read

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_dataset_sidebar.py \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar -q
# 22 passed for 0e2c125

poetry run ruff check \
  XBrainLab/ui/panels/dataset/sidebar.py \
  tests/unit/ui/dataset/test_dataset_sidebar.py \
  tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright \
  XBrainLab/ui/panels/dataset/sidebar.py \
  tests/unit/ui/dataset/test_dataset_sidebar.py \
  tests/unit/ui/test_sidebars_and_components.py
# passed for 0e2c125; basedpyright reported 0 errors, 0 warnings, 0 notes

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 0e2c125; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

poetry run pytest --capture=sys tests/unit/scripts/test_run_tool_call_eval.py -q
# 5 passed for 261c732

poetry run ruff check scripts/agent/evals/run_tool_call_eval.py tests/unit/scripts/test_run_tool_call_eval.py
poetry run basedpyright scripts/agent/evals/run_tool_call_eval.py tests/unit/scripts/test_run_tool_call_eval.py
# passed for 261c732; basedpyright reported 0 errors, 0 warnings, 0 notes

poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir /tmp/xbrainlab_det_gate_full
# exit 2 for 261c732; wrote deterministic_gate.json/.md and no latest.json

poetry run python scripts/agent/evals/run_tool_call_eval.py \
  --output-dir /tmp/xbrainlab_det_gate_case --case-id empty-load-path
# exit 0 for 261c732; wrote one-case latest.json/latest.md

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 261c732; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys \
  tests/unit/scripts/test_run_tool_call_eval.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 6 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q
# 19 passed for 8862d14

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
# exit 0 for 8862d14; status passed, forbidden visible text findings 0
# resource smoke passed; RSS growth 231556 KB / 600000 KB

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run mkdocs build --strict
poetry run python tests/architecture_compliance.py
# all passed for 8862d14; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/integration/ui/test_product_walkthrough.py -q
# 22 passed

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/training/test_training_panel.py::test_training_updated_observer_enters_refresh_coordinator \
  tests/unit/ui/training/test_training_panel.py::test_training_panel_refreshes_progress_and_plot_on_training_updated \
  tests/unit/ui/test_refresh_coordinator.py::test_training_updated_observer_uses_training_owner_scope -q
# 3 passed for 5c390da focused observer-routing regression

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/training/test_training_panel.py \
  tests/unit/ui/test_refresh_coordinator.py \
  tests/unit/ui/test_panel_event_bridges.py -q
# 56 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 5c390da; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q
# 19 passed for cd1a94b focused walkthrough unit regression

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
# exit 0 for cd1a94b; status passed, 26/26 phases, 20 screenshots
# ChatPanel visible_text now includes bubble text and chatpanel.visible_messages has 8 entries
# resource smoke passed; RSS growth 231884 KB / 600000 KB, Qt active threads 0

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for cd1a94b; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/integration/ui/test_product_walkthrough.py -q
# 22 passed

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/scripts/test_capture_data_interpretation_replay.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/integration/ui/test_product_walkthrough.py -q
# 46 passed for 2a711d4

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py
# exit 0; preview shows sub-01 run-2, remap shows full Needs review, apply mapping preserves full filename

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
# exit 0; status passed, 26/26 phases, 20 screenshots, resource smoke passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 2a711d4; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_dataset_sidebar.py \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  tests/unit/ui/styles/test_theme.py -q
# 36 passed for 2f5ccb0

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
# exit 0; status passed, 26/26 phases, 20 screenshots, resource smoke passed
# Clear Dataset: startup/reset disabled with "No dataset to clear.", apply enabled

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 2f5ccb0; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_dataset_sidebar.py \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  tests/unit/ui/styles/test_theme.py \
  tests/integration/ui/test_product_walkthrough.py -q
# 39 passed

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/components/test_info_panel_service.py \
  tests/unit/ui/test_main_window_sync.py \
  tests/unit/ui/test_refresh_coordinator.py \
  tests/unit/ui/test_panel_event_bridges.py \
  tests/integration/ui/test_e2e_qtbot.py::TestInfoService -q
# 56 passed for 48af56d

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 34 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 48af56d; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/integration/ui/test_product_walkthrough.py -q
# 21 passed for 6e99b03

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
# exit 0; claim boundary visible at top of 20-eval-dashboard.png

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 6e99b03; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q
# 17 passed

poetry run ruff format --check \
  scripts/dev/capture_human_like_product_walkthrough.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py
# 2 files already formatted

poetry run ruff check \
  scripts/dev/capture_human_like_product_walkthrough.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py
# All checks passed

poetry run basedpyright \
  scripts/dev/capture_human_like_product_walkthrough.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py
# 0 errors, 0 warnings, 0 notes

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
# exit 0; status passed, 26/26 phases, 20 screenshots

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for ca469ff; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py -q
# 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/ui/test_product_walkthrough.py -q
# 3 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_data_interpretation_replay.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_table_columns_fill_available_width \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_refits_table_after_loaded_rows_settle \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_events_column_uses_semantic_text_and_muted_color \
  -q
# 23 passed

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py
# exit 0

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
# exit 0; walkthrough status passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run mkdocs build --strict
poetry run python tests/architecture_compliance.py
# all passed; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_real_study_montage_refuses_controller_fallback \
  tests/unit/ui/test_refresh_coordinator.py \
  tests/unit/ui/test_panel_event_bridges.py \
  -q
# 46 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  tests/unit/ui/dataset/test_panel.py \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  -q
# 89 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  tests/unit/ui/training/test_training_panel.py \
  -q
# 50 passed

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 23 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar \
  tests/unit/ui/preprocess \
  -q
# 61 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
poetry run mkdocs build --strict
# all passed for a7b7222; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 24 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  tests/unit/ui/training/test_training_panel.py \
  -q
# 50 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for e309996; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  tests/unit/ui/dataset/test_dataset_sidebar.py \
  -q
# 16 passed

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 25 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 0c3de01; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  tests/unit/ui/test_panel_event_bridges.py \
  -q
# 22 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 699e829; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  -q
# 35 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 25022fe; basedpyright baseline refreshed from 115 to 112;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  -q
# 38 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 9327a4d; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  -q
# 39 passed for 7b3c3e7

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  -q
# 40 passed for d2e5b73

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_smart_parse \
  -q
# 67 passed for d0a66b2

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 28 passed for d0a66b2

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for the 7b3c3e7 / d2e5b73 / d0a66b2 UI query-truth slices;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  tests/unit/ui/training/test_training_panel.py \
  tests/unit/ui/training/test_training_setting.py \
  -q
# 60 passed for 7ab9501

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar \
  -q
# 23 passed for ebbdcfd

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 29 passed for ebbdcfd

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for bb005ab / ebbdcfd; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess -q
# 41 passed for feb9f88

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for feb9f88; basedpyright baseline decreased by 1;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/components/test_info_panel_service.py \
  tests/unit/ui/components/test_info_panel.py \
  -q
# 11 passed for 272dc5e

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 272dc5e; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_panel.py \
  -q
# 14 passed for 3f63592

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 3f63592; basedpyright baseline decreased by 1;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  -q
# 67 passed for 4f96005

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 4f96005; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  -q
# 11 passed for c6c7e5b

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for c6c7e5b; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q
# 112 passed for a00a5d5

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  -q
# 9 passed for a00a5d5

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for a00a5d5

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for a00a5d5

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for a00a5d5; basedpyright baseline decreased by 3;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q
# 114 passed for f2ccf95

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  -q
# 28 passed for f2ccf95

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for f2ccf95

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for f2ccf95

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for f2ccf95; basedpyright baseline decreased by 2;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q
# 114 passed for e067e73

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/training/test_training_panel.py \
  -q
# 18 passed for e067e73

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for e067e73

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for e067e73

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for e067e73; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  -q
# 42 passed for c21d7eb

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_state_service.py \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  tests/unit/ui/test_data_splitting.py \
  tests/unit/ui/dialogs/test_data_splitting.py \
  -q
# 114 passed for 4ddfa92

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q
# 114 passed for 4ddfa92

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for c21d7eb / 4ddfa92

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for c21d7eb / 4ddfa92

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for c21d7eb and 4ddfa92; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_data_splitting.py \
  tests/unit/ui/dialogs/test_data_splitting.py \
  tests/unit/ui/dataset/test_data_splitting.py \
  tests/unit/ui/test_panels_and_dialogs.py \
  -q
# 105 passed for 51a6149

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 51a6149

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 51a6149

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 51a6149; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys \
  tests/unit/llm/core/test_downloader.py \
  tests/unit/llm/test_coverage_boost.py::TestDownloadWorkerRun \
  tests/unit/llm/test_misc_coverage.py::TestModelDownloaderCoverage \
  tests/unit/test_llm_backend.py::TestDownloader \
  -q
# 27 passed for 435d9a9

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/test_model_settings.py \
  tests/unit/ui/test_local_bootstrap_validation.py \
  -q
# 25 passed for 435d9a9

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 435d9a9; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys \
  tests/unit/llm/core/test_local_backend.py \
  tests/unit/llm/core/test_engine.py \
  tests/unit/llm/core/test_backend_local.py \
  tests/unit/llm/core/test_engine_hotswap.py \
  -q
# 37 passed for 5940b7d

poetry run pytest --capture=sys \
  tests/unit/llm/agent/test_worker.py \
  tests/unit/llm/test_worker_coverage.py \
  tests/unit/llm/agent/test_worker_timeout.py \
  -q
# 39 passed for 5940b7d

poetry run pytest --capture=sys \
  tests/unit/llm/agent/test_controller.py \
  tests/unit/llm/agent/test_controller_cov.py \
  tests/unit/llm/agent/test_controller_integration.py \
  -q
# 99 passed for 5940b7d

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 5940b7d; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys \
  tests/unit/backend/training/test_trainer.py \
  tests/unit/backend/test_training_manager.py \
  -q
# 40 passed for 5ff0790

poetry run pytest --capture=sys \
  tests/unit/backend/controller/test_training_controller.py \
  tests/unit/backend/application/test_training_service.py \
  tests/unit/backend/application/test_lifecycle_service.py \
  -q
# 19 passed for 5ff0790

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 5ff0790

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 5ff0790; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_clear_plot_schedules_child_widgets_for_deletion \
  tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_clear_plot \
  tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_update_plot_blocks_offscreen_before_qtinteractor \
  -q
# 3 passed for 9a5d0ef

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/components/test_plot_figure_window.py \
  -q
# 59 passed for 9a5d0ef

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 9a5d0ef

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 9a5d0ef

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 9a5d0ef; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_rereference_uses_query_data_list_before_stale_controller \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_rereference_accepted \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_query_data_list_before_stale_controller \
  -q
# 3 passed for d8221bb

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar \
  tests/unit/ui/preprocess \
  -q
# 65 passed for d8221bb

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for d8221bb

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for d8221bb

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for d8221bb; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/preprocess/test_preprocess_plotter.py::test_stale_psd_result_does_not_update_latest_plot \
  tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_async_psd \
  tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_time_domain \
  -q
# 3 passed for 28c144a

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/preprocess/test_preprocess_plotter.py \
  tests/unit/ui/preprocess \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar \
  -q
# 45 passed for 28c144a

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 28c144a

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 28c144a

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 28c144a; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_components.py::TestSinglePlotWindow::test_close_releases_current_figure_and_qt_widgets \
  tests/unit/ui/test_ui_components.py::TestSinglePlotWindow::test_creates \
  tests/unit/ui/test_ui_components.py::TestSinglePlotWindow::test_has_figure_canvas \
  -q
# 3 passed for f9acb77

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_components.py::TestSinglePlotWindow \
  tests/unit/ui/components/test_plot_figure_window.py \
  tests/unit/ui/dialogs/test_dialogs_structure.py::TestDialogStructure::test_single_plot_window_init \
  -q
# 19 passed for f9acb77

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for f9acb77

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for f9acb77

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for f9acb77; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_close_releases_figure_and_canvas \
  tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_replace_figure_releases_previous_canvas \
  tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_update_plot_no_eval \
  tests/unit/ui/test_visualization.py::TestSaliencySpectrogramWidget::test_update_plot_no_eval \
  tests/unit/ui/test_visualization.py::TestSaliencyTopographicMapWidget::test_update_plot_no_eval \
  -q
# 5 passed for 5ab35ba

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/components/test_plot_figure_window.py \
  -q
# 61 passed for 5ab35ba

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 5ab35ba

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 5ab35ba

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 5ab35ba; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_components.py::TestConfusionMatrix::test_update_none_releases_previous_canvas_and_children \
  tests/unit/ui/test_ui_components.py::TestConfusionMatrix::test_creates \
  tests/unit/ui/test_ui_components.py::TestConfusionMatrix::test_update_plot_no_data \
  -q
# 3 passed for 62b7f64

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  tests/unit/ui/test_panel_event_bridges.py \
  tests/unit/ui/test_ui_components.py::TestConfusionMatrix \
  tests/unit/ui/test_ui_components.py::TestMetricsBarChart \
  -q
# 29 passed for 62b7f64

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 62b7f64

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 62b7f64

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 62b7f64; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_close_releases_figure_and_canvas \
  tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_creates \
  tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_update_plot_no_data \
  tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_update_plot_layout_failure_is_not_logged_as_error \
  -q
# 4 passed for 3ecb698

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  tests/unit/ui/test_panel_event_bridges.py \
  tests/unit/ui/test_ui_components.py::TestConfusionMatrix \
  tests/unit/ui/test_ui_components.py::TestMetricsBarChart \
  -q
# 30 passed for 3ecb698

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 3ecb698

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 3ecb698

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 3ecb698; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  tests/unit/ui/dataset/test_panel.py \
  tests/unit/ui/dataset/test_import_label.py \
  -q
# 105 passed for b6b6d00

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for b6b6d00

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for b6b6d00

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for b6b6d00; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_refuses_real_study_query_none_controller_fallback \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_refuses_real_study_query_none_controller_fallback \
  -q
# 2 passed for a315170 after red failures on stale controller list reads

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  -q
# 37 passed for a315170

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_dataset_sidebar.py \
  tests/unit/ui/preprocess/test_preprocess_plotter.py \
  tests/unit/ui/preprocess/test_data_query.py \
  -q
# 31 passed for a315170

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for a315170

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for a315170

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for a315170; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/preprocess/test_preprocess_panel.py::test_update_panel_refuses_real_study_query_none_controller_fallback \
  tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_refuses_real_study_query_none_controller_fallback \
  -q
# 2 passed for a86b1b2 after red failures on stale Preprocess controller reads

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/preprocess \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar \
  -q
# 73 passed for a86b1b2

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for a86b1b2

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for a86b1b2

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for a86b1b2; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_export_saliency_refuses_real_study_query_none_controller_fallback \
  tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_refuses_real_study_controller_fallback \
  tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_apply_none_refuses_real_study_controller_fallback \
  tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_refuses_real_study_controller_fallback \
  tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_apply_none_refuses_real_study_controller_fallback \
  -q
# 5 passed for 3330f1d after red failures where fallback refusal escaped as an exception

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  tests/unit/ui/test_visualization.py \
  -q
# 64 passed for 3330f1d

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 3330f1d

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 3330f1d

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 3330f1d; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_evaluation_panel_redesign.py::test_evaluation_panel_refuses_real_study_query_none_controller_fallback \
  -q
# 1 passed for fdea34a after red failure on stale EvaluationController.get_plans()

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  tests/unit/ui/test_ui_structure_refactored.py \
  -q
# 12 passed for fdea34a

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for fdea34a

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for fdea34a

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for fdea34a; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization_panel_redesign.py::test_visualization_panel_refuses_real_study_query_none_controller_fallback \
  -q
# 1 passed for 18f2c87 after red failure on stale VisualizationController.get_trainers()

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  tests/unit/ui/test_visualization.py \
  -q
# 65 passed for 18f2c87

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 18f2c87

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 18f2c87

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 18f2c87; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/training/test_training_panel.py::test_training_panel_refuses_real_study_query_none_controller_history \
  -q
# 1 passed for bdfebfa after red failure on stale TrainingController.get_formatted_history()

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/training/test_training_panel.py \
  tests/unit/ui/test_panel_event_bridges.py \
  -q
# 33 passed for bdfebfa

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for bdfebfa

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for bdfebfa

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for bdfebfa; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_evaluation_panel_redesign.py::test_evaluation_panel_refuses_real_study_query_none_metric_fallback \
  -q
# 1 passed for c7d13ca after red failure on unstable last_application_query in the stale-selection path

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  tests/unit/ui/test_ui_structure_refactored.py \
  -q
# 13 passed for c7d13ca

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for c7d13ca

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for c7d13ca

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for c7d13ca; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization_panel_redesign.py::test_visualization_panel_refuses_real_study_query_none_average_fallback \
  -q
# 1 passed for 7fc1027 after red failure on stale VisualizationController.get_averaged_record()

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  tests/unit/ui/test_visualization.py \
  -q
# 66 passed for 7fc1027

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 7fc1027

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 7fc1027

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 7fc1027; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_stop_training_refuses_real_study_controller_fallback \
  -q
# 1 passed for 85b4200 after red failure on escaped LegacyControllerFallbackUnavailableError

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  -q
# 35 passed for 85b4200

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 85b4200

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 85b4200

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 85b4200; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_clear_history_refuses_real_study_controller_fallback \
  -q
# 1 passed for 9c81f4d after red failure on generic Warning / Error clearing history text

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  -q
# 36 passed for 9c81f4d

poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# focused lint/type passed for 9c81f4d

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 9c81f4d

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 9c81f4d

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 9c81f4d; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_refuses_real_study_controller_fallback \
  -q
# 1 passed for 6f6ca72 after red failure on generic critical reset failure

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar \
  -q
# 25 passed for 6f6ca72

poetry run ruff check XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# focused lint/type passed for 6f6ca72

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 6f6ca72

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 6f6ca72

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 6f6ca72; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_clear_dataset_refuses_real_study_controller_fallback \
  -q
# 1 passed for dc3c486 after red failure on missing blocked warning

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  -q
# 13 passed for dc3c486

poetry run ruff check XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# focused lint/type passed for dc3c486

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for dc3c486

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for dc3c486

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for dc3c486; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_refuses_real_study_apply_none_controller_fallback \
  -q
# 1 passed for ea16c8b after red failure on missing blocked warning

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  -q
# 14 passed for ea16c8b

poetry run ruff check XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# focused lint/type passed for ea16c8b

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for ea16c8b

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for ea16c8b

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for ea16c8b; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_refuses_real_study_generate_none_controller_fallback \
  -q
# 1 passed for c93012d after red failure on escaped legacy fallback exception

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  -q
# 37 passed for c93012d

poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# focused lint/type passed for c93012d

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for c93012d

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for c93012d

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for c93012d; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_refuses_real_study_clear_none_controller_fallback \
  -q
# 1 passed for cdab73f after red failure on escaped legacy fallback exception

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  -q
# 38 passed for cdab73f

poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# focused lint/type passed for cdab73f

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for cdab73f

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for cdab73f

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for cdab73f; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_refuses_real_study_controller_fallback \
  -q
# 1 passed for 78c53d1 after red failure on escaped legacy fallback exception

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  -q
# 39 passed for 78c53d1

poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# focused lint/type passed for 78c53d1

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 78c53d1

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 78c53d1

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 78c53d1; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_training_setting_refuses_real_study_controller_fallback \
  -q
# 1 passed for 9abb334 after red failure on escaped legacy fallback exception

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  -q
# 40 passed for 9abb334

poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# focused lint/type passed for 9abb334

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 9abb334

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 9abb334

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 9abb334; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_refuses_real_study_controller_fallback \
  -q
# 1 passed for 5ad6b7d after red failure on missing blocked warning

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  -q
# 41 passed for 5ad6b7d

poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# focused lint/type passed for 5ad6b7d

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 5ad6b7d

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 5ad6b7d

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 5ad6b7d; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_refuses_real_study_query_none_dialog_context \
  -q
# 1 passed for e8e65bc after red failure because the dialog opened

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  -q
# 42 passed for e8e65bc

poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# focused lint/type passed for e8e65bc

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for e8e65bc

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for e8e65bc

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_refuses_real_study_controller_fallback \
  -q
# red first on escaped legacy fallback exception, then 1 passed for be0f188

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  -q
# 68 passed for be0f188

poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
# passed for be0f188; basedpyright reported 0 errors, 0 warnings, 0 notes

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
poetry run pytest --capture=sys tests/integration/backend -q
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# passed for be0f188; backend integration 7 passed; agent/tool gate 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_batch_set_refuses_real_study_controller_fallback \
  -q
# red first on escaped legacy fallback exception, then 1 passed for e5d1e20

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  -q
# 69 passed for e5d1e20

poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
# passed for e5d1e20; basedpyright reported 0 errors, 0 warnings, 0 notes

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
poetry run pytest --capture=sys tests/integration/backend -q
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# passed for e5d1e20; backend integration 7 passed; agent/tool gate 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_refuses_real_study_controller_fallback \
  -q
# red first on escaped legacy fallback exception, then 1 passed for eed6066

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  -q
# 70 passed for eed6066

poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
# passed for eed6066; basedpyright reported 0 errors, 0 warnings, 0 notes

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
poetry run pytest --capture=sys tests/integration/backend -q
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# passed for eed6066; backend integration 7 passed; agent/tool gate 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_refuses_real_study_controller_fallback \
  -q
# red first because the fallback refusal was shown as generic Failed text, then 1 passed for 6f06503

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  -q
# 71 passed for 6f06503

poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
# passed for 6f06503; basedpyright reported 0 errors, 0 warnings, 0 notes

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
poetry run pytest --capture=sys tests/integration/backend -q
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# passed for 6f06503; backend integration 7 passed; agent/tool gate 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_refuses_real_study_filename_fallback \
  -q
# red first on escaped legacy fallback exception, then 1 passed for 724447b

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  -q
# 72 passed for 724447b

poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
# passed for 724447b; basedpyright reported 0 errors, 0 warnings, 0 notes

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
poetry run pytest --capture=sys tests/integration/backend -q
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# passed for 724447b; backend integration 7 passed; agent/tool gate 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_refuses_real_study_direct_load_fallback \
  -q
# red first because no blocked warning was shown, then 1 passed for 3d1321a

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  -q
# 73 passed for 3d1321a

poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py
# passed for 3d1321a; basedpyright reported 0 errors, 0 warnings, 0 notes

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
poetry run pytest --capture=sys tests/integration/backend -q
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# passed for 3d1321a; backend integration 7 passed; agent/tool gate 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_filtering_refuses_real_study_controller_fallback \
  -q
# red first because no blocked warning was shown, then 1 passed for fc14dd3

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar \
  -q
# 26 passed for fc14dd3

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess -q
# 48 passed for fc14dd3

poetry run pytest --capture=sys \
  tests/unit/test_architecture_compliance.py::test_controller_fallback_guard_allows_named_legacy_wrapper \
  tests/unit/test_architecture_compliance.py::test_controller_fallback_guard_flags_direct_mutation_in_missing_result \
  tests/unit/test_architecture_compliance.py::test_direct_controller_mutation_guard_allows_named_legacy_wrapper_call \
  -q
# 3 passed for fc14dd3

poetry run ruff check XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py
poetry run basedpyright XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py
# passed for fc14dd3; basedpyright reported 0 errors, 0 warnings, 0 notes

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
poetry run mkdocs build --strict
poetry run pytest --capture=sys tests/integration/backend -q
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# passed for fc14dd3; architecture unit 32 passed; backend integration 7 passed; agent/tool 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_metadata_edit_refuses_real_study_controller_fallback \
  -q
# red first on escaped legacy fallback exception, then 1 passed for c26cb99

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_panel.py \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  -q
# 88 passed for c26cb99

poetry run ruff check XBrainLab/ui/panels/dataset/panel.py tests/unit/ui/dataset/test_panel.py
poetry run basedpyright XBrainLab/ui/panels/dataset/panel.py tests/unit/ui/dataset/test_panel.py
# passed for c26cb99; basedpyright reported 0 errors, 0 warnings, 0 notes

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
poetry run pytest --capture=sys tests/integration/backend -q
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# passed for 41930e0; backend integration 7 passed; agent/tool 20 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/test_architecture_compliance.py \
  -q
# 34 passed for 83b0015

poetry run python tests/architecture_compliance.py
# Architecture compliant for 83b0015

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_panel.py \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  tests/unit/scripts/test_capture_data_interpretation_replay.py \
  -q
# 35 passed for e79d3b6

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_agent_manager_coverage.py \
  tests/unit/ui/components/test_agent_manager.py \
  tests/unit/ui/test_ui_misc.py::TestAgentManagerDeep \
  -q
# 83 passed for 41930e0

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for e8e65bc; mkdocs still prints the existing Material advisory
```

No local LLM eval was run for these UI / architecture / lifecycle guard slices.

## Tool-Call Eval Gate Policy

Do not run full primary/fallback x3 local eval for routine changes.

- Fast dev gate:
  - deterministic eval
  - changed / failed cases only
  - repeat `1`
  - no fallback model
- Candidate gate:
  - primary model only
  - affected case families
  - repeat `1` or `2`
- Release / thesis gate:
  - deterministic full suite
  - primary full suite x3
  - fallback full suite x3
  - dashboard refresh
  - record disk / cache / `nvidia-smi` VRAM used/free, latency, and resource pressure

RTX 5070 Ti 16GB has already shown near-full VRAM pressure on fallback x3. If VRAM is nearly full,
do not start a full fallback x3 run. Use deterministic changed cases or primary subset unless the
work is explicitly a release / thesis evidence gate. The local eval CLI now also requires
full-suite repeat `3` local runs to declare `--eval-gate release` or `--eval-gate thesis`; the
default candidate gate writes `resource_preflight.*` and exits before model startup.
The deterministic CLI now mirrors this layering: default `fast` runs require an explicit subset and
repeat `1`, while full-suite deterministic dashboard refreshes require `--eval-gate release` or
`--eval-gate thesis`.

## Still Cannot Claim Product Complete

- UI refresh remains partially mixed:
  - command-result coordinator baseline exists, but observer/manual/tab-switch/event-specific
    refreshes still remain.
- Product runtime controller fallback is still an audit target:
  - controller fallback must stay explicit mock / unit-test / legacy-only, not silent product
    runtime mutation.
- Data Interpretation is stronger but not final:
  - embedded label editor, raw trigger selector, complex GDF/MAT anchor reconciliation, XDF/LSL full
    parser, full real-data manual certification, and recipe diff/review UX remain.
- Human desktop acceptance remains open:
  - Windows launcher click-through, dual monitor / DPI, and long real local-model desktop session
    are not verified.
- Agent / MCP release depth remains open:
  - long autonomous ChatPanel workflow, UI-routing render, full recovery behavior, HTTP MCP
    transport, and long-running MCP job progress/cancel/recovery remain.
- Tool-call benchmark evidence must not be used as UI / launcher / import wizard product evidence.

## Suggested Next Slices

1. Continue `UI Command Refresh Coordinator + Controller Fallback Audit`.
   - Audit remaining `result is None` branches and controller read echoes.
   - Keep product runtime mutations on ApplicationService, with controller fallback only in explicit
     mock / legacy branches.
   - Continue routing post-command refresh through the coordinator.
2. Continue Data Interpretation wizard maturity.
   - Add a small recipe diff/review UX slice or a safer label-carrier edit slice with screenshot
     artifact.
3. Only after product/UI/backend path stabilizes, refresh affected tool-call eval cases using the
   fast/candidate gate. Reserve full primary/fallback x3 for release/thesis evidence.
