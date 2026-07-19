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
| BIDS events.tsv | sub-01_ses-01_task-mi_run-1_events.tsv | BIDS events | external_labels | needs_review | blocked | BIDS events use onset and duration with label columns such as trial_type or value; review event column and sidecar semantics. |
| CSV labels | labels.csv | CSV / TSV labels | external_labels | needs_review | blocked | CSV / TSV labels require label column, anchor, time model, and granularity confirmation. |
| TSV labels | labels.tsv | CSV / TSV labels | external_labels | needs_review | blocked | CSV / TSV labels require label column, anchor, time model, and granularity confirmation. |
| TXT labels | labels.txt | TXT labels | external_labels | needs_review | blocked | Text label sequences require trial-order or anchor alignment confirmation. |
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

## Real Data Interpretation Workflows

Every row passes only after `scan -> preview -> validate -> apply`. Public fixture workflows, checked-in/derived formats, and generated parser contracts are reported in separate evidence layers.

### Public dataset-source evidence

Hash-pinned public fixtures. These rows alone count toward public dataset-source diversity.

| Scope | Source family | Format | Evidence tier | Validation | Label apply | Epoch handoff | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| public_source | PhysioNet | EDF | not_required | needs_confirmation | not_applicable | raw/import only | passed |
| public_source | PhysioNet | EDF | supervised | needs_confirmation | not_applicable | supervised ready | passed |
| public_source | BBCI | GDF | supervised | needs_confirmation | not_applicable | supervised ready | passed |
| public_source | SCCN / EEGLAB | EEGLAB SET | io_epoch_only | needs_confirmation | not_applicable | epoch smoke separate | passed |
| public_source | MNE testing-data | CNT | io_epoch_only | needs_confirmation | not_applicable | epoch smoke separate | passed |
| public_source | MNE testing-data | BrainVision | not_required | needs_confirmation | not_applicable | raw/import only | passed |
| public_source | MNE-BIDS | BIDS EEG / BrainVision | label_apply_only | safe | applied | raw/import only | passed |

### Checked-in and derived-format evidence

Checked-in source data and compact format derivatives. Derived formats add format coverage, not independent source diversity.

| Scope | Source family | Format | Evidence tier | Validation | Label apply | Epoch handoff | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| checked_in_source | Graz / BCI Competition IV 2a | GDF + MAT labels | supervised | needs_confirmation | applied | supervised ready | passed |
| derived_format | Graz A01T derived formats | FIF | not_required | needs_confirmation | not_applicable | raw/import only | passed |
| derived_format | Graz A01T derived formats | FIF.GZ | not_required | needs_confirmation | not_applicable | raw/import only | passed |
| derived_format | Graz A01T derived formats | Epoched FIF | not_required | needs_confirmation | not_applicable | raw/import only | passed |
| derived_format | Graz A01T derived formats | EDF | not_required | needs_confirmation | not_applicable | raw/import only | passed |
| derived_format | Graz A01T derived formats | BDF | not_required | needs_confirmation | not_applicable | raw/import only | passed |
| derived_format | Graz A01T derived formats | BrainVision | not_required | needs_confirmation | not_applicable | raw/import only | passed |
| derived_format | Graz A01T derived formats | EEGLAB SET | not_required | needs_confirmation | not_applicable | raw/import only | passed |

### Generated contract evidence

Generated valid EEG/label fixtures exercise declared parser and placement contracts only. They are not public dataset, protocol, or training evidence.

| Scope | Source family | Format | Evidence tier | Validation | Label apply | Epoch handoff | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| generated_contract | Generated contract fixture | CSV labels | generated_supervised_contract | needs_confirmation | applied | generated contract only | passed |
| generated_contract | Generated contract fixture | CSV labels | generated_supervised_contract | safe | applied | generated contract only | passed |
| generated_contract | Generated contract fixture | TSV labels | generated_supervised_contract | safe | applied | generated contract only | passed |
| generated_contract | Generated contract fixture | CSV labels | generated_supervised_contract | needs_confirmation | applied | generated contract only | passed |
| generated_contract | Generated contract fixture | TXT labels | generated_supervised_contract | needs_confirmation | applied | generated contract only | passed |

### Real workflow summary

- Public fixture workflow layer: `7 / 7`
- Checked-in and derived-format layer: `8 / 8`
- Generated contract layer: `5 / 5` (excluded from public source diversity)
- Required cases: `20 / 20` passed
- Public source families completing the lifecycle: `5` BBCI, MNE testing-data, MNE-BIDS, PhysioNet, SCCN / EEGLAB
- Required formats completing the lifecycle: `14 / 14`
- Cross-layer external label placement contracts: `7 / 7`
- Reviewed public internal-event profiles: `4 / 4`
- Fixed cross-layer reviewed-label/event workflows: `11 / 11`
- Pinned public fixture fact contracts: `7 / 7`
- Strict real-workflow result: `True`

### Pinned public fixture facts

| Case ID | Hz | Channels / types | Canonical / source units | Samples | Embedded events | Import warnings | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| public_physionet_rest_edf | 160.0 | 64 / {"eeg": 64} | {"V": 64} / {"uV": 64} | 9760 | 1 | 0 | passed |
| public_physionet_motor_edf | 160.0 | 64 / {"eeg": 64} | {"V": 64} / {"uV": 64} | 19680 | 30 | 0 | passed |
| public_bbci_gdf | 125.0 | 2 / {"eeg": 2} | {"V": 2} / {"unknown": 2} | 729558 | 2560 | 1 | passed |
| public_sccn_eeglab | 128.0 | 32 / {"eeg": 32} | {"V": 32} / {"unknown": 32} | 30504 | 154 | 0 | passed |
| public_mne_cnt | 400.0 | 128 / {"eeg": 128} | {"V": 128} / {"unknown": 128} | 3070 | 6 | 2 | passed |
| public_mne_brainvision | 5000.0 | 65 / {"eeg": 65} | {"V": 65} / {"uV": 65} | 2238 | 0 | 0 | passed |
| public_mne_bids_eeg | 5000.0 | 69 / {"eeg": 67, "misc": 2} | {"V": 67, "degC": 1, "none": 1} / {"C": 1, "S": 1, "uV": 67} | 10000 | 1 | 0 | passed |

### Real workflow claim boundary

- Supports: Seven hash-pinned public fixture workflows across five source families, eight checked-in or derived-format fixtures, and five generated parser/placement contracts completed the scan, preview, validate, and apply command lifecycle in separate evidence layers. Public fixtures also matched pinned sampling, channel/type/unit, sample/event, and import-warning facts. The fixed 11-case reviewed-choice set preserved its explicit choices and required evidence tiers.
- Does not support: A passing lifecycle does not prove arbitrary files, scientific class semantics, full BIDS compliance, or source diversity for A01T-derived format conversions. Generated CSV, TSV, and TXT fixtures prove only the declared parser and placement contracts; they do not add public dataset-source diversity or certify arbitrary carrier schemas. SCCN rt/square and CNT marker evidence is IO/epoch only, not protocol-grounded supervised-class or training evidence.
