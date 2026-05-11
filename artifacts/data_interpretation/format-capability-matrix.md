# Data Interpretation Format Capability Matrix

Generated from the live ApplicationService command path:

- `ScanSourceCommand`
- `PreviewInterpretationCommand`
- `ValidateInterpretationCommand`

| Coverage | Source fixture | Detected format | Role | Status | Validation | Boundary |
| --- | --- | --- | --- | --- | --- | --- |
| GDF recording | sub-01_ses-01_task-mi_run-1.gdf | GDF | eeg | needs_review | needs_confirmation | GDF event tables often mix trial starts, cues, artifacts, and class events; confirm trial anchor, class map, and external label alignment before supervised training. |
| MAT labels | sub-01_ses-01_task-mi_run-1.mat | MAT labels | external_labels | needs_review | needs_confirmation | MAT labels require variable selection, anchor alignment, and class map confirmation. |
| EDF recording | sub-01_ses-01_task-rest_run-1.edf | EDF | eeg | needs_review | needs_confirmation | EDF / BDF annotations can describe events or intervals; review annotation roles, time units, and class map before supervised training. |
| BDF recording | sub-01_ses-01_task-rest_run-2.bdf | EDF | eeg | needs_review | needs_confirmation | EDF / BDF annotations can describe events or intervals; review annotation roles, time units, and class map before supervised training. |
| EEGLAB SET | sub-01_ses-01_task-mi_run-1.set | EEGLAB | eeg | needs_review | needs_confirmation | EEGLAB events, urevents, and boundary markers require review; boundary must not be treated as a class label. |
| BrainVision VHDR | sub-01_ses-01_task-mi_run-1.vhdr | BrainVision | eeg | needs_review | needs_confirmation | BrainVision marker sidecars can include stimulus, response, sync, and new segment markers; review event roles before apply. |
| BrainVision VMRK | sub-01_ses-01_task-mi_run-1.vmrk | BrainVision markers | sidecar | context | needs_confirmation | BrainVision marker sidecar detected; use the associated .vhdr source and review marker roles. |
| MNE FIF | sub-01_ses-01_task-rest_run-1_raw.fif | MNE FIF | eeg | supported | safe | FIF can be loaded as an EEG recording; review metadata and events before supervised training. |
| BIDS events.tsv | sub-01_ses-01_task-mi_run-1_events.tsv | BIDS events | external_labels | needs_review | needs_confirmation | BIDS events use onset and duration with label columns such as trial_type or value; review event column and sidecar semantics. |
| CSV labels | labels.csv | CSV / TSV labels | external_labels | needs_review | needs_confirmation | CSV / TSV labels require label column, anchor, time model, and granularity confirmation. |
| TSV labels | labels.tsv | CSV / TSV labels | external_labels | needs_review | needs_confirmation | CSV / TSV labels require label column, anchor, time model, and granularity confirmation. |
| TXT labels | labels.txt | TXT labels | external_labels | needs_review | needs_confirmation | Text label sequences require trial-order or anchor alignment confirmation. |
| XDF / LSL stream export | session01_streams.xdf | XDF / LSL | device_export | blocked | blocked | XDF / LSL stream selection is not available in this import wizard yet. Convert streams to a supported EEG format or provide a prepared recipe. |

## Summary

- Cases: `9`
- Matrix rows: `13`
- Statuses: `blocked`, `context`, `needs_review`, `supported`
- Validation decisions: `blocked`, `needs_confirmation`, `safe`
- All expected capabilities observed: `True`
- All expected capabilities match: `True`

## Claim Boundary

- Supports: Data Interpretation scan, preview, and validation expose user-facing format capability boundaries for representative EEG recordings, label carriers, BIDS events, and blocked XDF / LSL stream exports.
- Does not support: This matrix does not implement an XDF / LSL stream parser, raw-event-anchor-specific GDF / MAT alignment, or a full manual compatibility certification across real public datasets.
