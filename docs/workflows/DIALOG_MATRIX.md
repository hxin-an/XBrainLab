# XBrainLab Dialog Matrix

This document tracks the main dialogs in the application and why they matter during stabilization.

The goal is to make modal workflow review concrete instead of ad hoc.

## How To Use This Matrix

For each dialog, we care about:

- what workflow it belongs to
- whether it is configuration-critical or convenience-only
- what kind of failure would hurt most
- whether the current test harness is likely to miss live issues

## Dataset Dialogs

| Dialog | Workflow Role | Risk | Typical Failure Mode |
|---|---|---|---|
| `channel_selection_dialog.py` | channel filtering/setup | Medium | selection not applied or UI state drift |
| `data_splitting_dialog.py` | training prep entry from dataset/training flow | High | invalid split accepted or reset side effects unclear |
| `data_splitting_preview_dialog.py` | preview before applying split | Medium | preview mismatch versus final split |
| `event_filter_dialog.py` | label import event narrowing | High | wrong events selected or cancellation mishandled |
| `import_label_dialog.py` | label import entrypoint | High | wrong mapping mode or silent failure |
| `label_mapping_dialog.py` | batch label-to-data pairing | High | mismatched file mapping |
| `manual_split_dialog.py` | manual split editing | Medium | split state not persisted correctly |
| `smart_parser_dialog.py` | filename metadata parsing | Medium | unexpected parse result or overwrite confusion |

## Preprocess Dialogs

| Dialog | Workflow Role | Risk | Typical Failure Mode |
|---|---|---|---|
| `epoching_dialog.py` | turns continuous data into training-ready epochs | High | invalid epoch config or lock-state transition issues |
| `filtering_dialog.py` | filter configuration | Medium | invalid frequency handling or misleading defaults |
| `normalize_dialog.py` | normalization setup | Medium | option accepted but not reflected downstream |
| `rereference_dialog.py` | re-reference setup | Medium | channel selection mismatch |
| `resampling_dialog.py` | resample setup | Medium | output rate mismatch or stale preview |

## Training Dialogs

| Dialog | Workflow Role | Risk | Typical Failure Mode |
|---|---|---|---|
| `device_setting_dialog.py` | device/backend selection | Medium | invalid device state or hidden incompatibility |
| `model_selection_dialog.py` | model choice | High | model shown as selected but not actually applied |
| `optimizer_setting_dialog.py` | optimizer settings | Medium | values accepted but not used consistently |
| `training_setting_dialog.py` | hyperparameter setup | High | readiness logic and saved settings disagree |

## Visualization Dialogs

| Dialog | Workflow Role | Risk | Typical Failure Mode |
|---|---|---|---|
| `export_saliency_dialog.py` | result export | Medium | export path or content mismatch |
| `montage_picker_dialog.py` | channel position setup | High | montage applies incorrectly and distorts views |
| `saliency_setting_dialog.py` | saliency algorithm settings | High | settings saved but current tab not refreshed correctly |

## Cross-Cutting Review Notes

- Many dialogs are likely underrepresented in live-behavior testing because `QDialog.exec` is patched in the unit test harness.
- High-risk dialogs should be reviewed with both logic-level tests and at least one real interactive validation pass.
- Dialogs that mutate shared state should be treated as workflow boundaries, not isolated widgets.

## Suggested Review Order

1. `import_label_dialog.py`
2. `label_mapping_dialog.py`
3. `event_filter_dialog.py`
4. `epoching_dialog.py`
5. `training_setting_dialog.py`
6. `model_selection_dialog.py`
7. `montage_picker_dialog.py`
8. `saliency_setting_dialog.py`
