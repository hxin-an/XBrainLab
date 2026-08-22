---
title: Lee2021Mobile ERP
case_id: moabb-lee2021mobile-erp
evidence_record: case-studies/manifests/moabb-lee2021mobile-erp.yml
publication_status: unverified
generated_from: moabb-datasets-v1
---

# Lee2021Mobile ERP

| | This guide uses |
| --- | --- |
| Paradigm | p300_erp |
| Scope | Subject(s) 1; session(s) 01; run(s) task-ERP; BrainVision source |
| Source format | BrainVision |
| Published run | Unverified |

This guide defines inputs and review checks. It does not publish a completed XBrainLab run, metric, or saliency result.

## Run this dataset

Continue only while the selected files, labels, and visible checks match this page.

### Source and version

- Dataset: [Mobile BCI dataset of scalp- and ear-EEGs with ERP and SSVEP paradigms while standing, walking and running](https://osf.io/r7s9b/).
- Dataset DOI: [doi:10.6084/m9.figshare.c.5311787](https://doi.org/10.6084/m9.figshare.c.5311787).
- Repository and license: OSF, `CC-BY-4.0`.
- MOABB adapter: [version 1.5.0 at 140809d8c48b](https://github.com/NeuroTechX/moabb/blob/140809d8c48bdf2be953951ff75f688122edee34/moabb/datasets/lee2021_mobile.py); [dataset reference](https://moabb.neurotechx.com/docs/generated/moabb.datasets.Lee2021Mobile_ERP.html).
- Site source contract: [moabb-compact-user-journeys-v1](../assets/manifests/moabb-datasets-v1.json), SHA-256 `61097550c8fb6afeb9156c9fbe9207f471eb2d04799cf16672ac4937686a70b9`.

- `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_eeg.eeg`: `sha256` `e0f401243f39cd76e285591db999c4b16070498530763c2ddb8f5b81d54c4084` ([source](https://osf.io/download/hu2rs/))
- `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_eeg.vhdr`: `sha256` `96eff453d24fa3e21ea161540761fb2c9bfab346a8f24902b8365e86c8dcd087` ([source](https://osf.io/download/jvpw4/))
- `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_eeg.vmrk`: `sha256` `f1918a726c653eb8c5fce9e0f310efd01d09a8560381924326923220838162e2` ([source](https://osf.io/download/ryj9k/))
- `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_channels.tsv`: `sha256` `4248434418108460907a76526038707b09b8bc2ae208feac649297f90dbd783c` ([source](https://osf.io/download/jmxhk/))
- `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_events.tsv`: `sha256` `508d2cc22afd4065b820faa376689eb2ccf9f5faf5cccd9114c16ea02cc5b65b` ([source](https://osf.io/download/j695x/))

### App action

1. Obtain only the files listed above and verify every checksum before opening the app.
2. Open **Dataset** in XBrainLab.
3. Use **Import file** and select `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_eeg.vhdr`.
4. Keep the import review open until the selected files and labels match this page.

### Choices

- Use `embedded_events` as the label carrier.
- `sub-01_ses-01_task-ERP_eeg.vhdr`: `Stimulus/S  1` = NonTarget, `Stimulus/S  2` = Target.
- Preprocess: band-pass `0.5` to `20.0` Hz.
- Epoch: `-0.25` to `1.0` s, baseline `None`.
- Split: `0.2` test and `0.2` validation by `trial`; `individual` training.
- Planned training: `EEGNet` on `cpu`, up to `30` epochs, batch `32`, learning rate `0.001`, checkpoint choice `val_auc`.

### Expected checkpoint

- Selected EEG files: `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_eeg.vhdr`.
- Resolved labels: `Target`, `NonTarget`.
- Status: pending visual confirmation in an identified XBrainLab run.

### Stop condition

Stop before preprocessing if a checksum differs, the selected file set changes, a run-specific label maps differently, or the app does not expose the stated choice. Do not substitute values or interpret later output as evidence for this route.

### Next step

After the import checkpoint matches, apply the settings one stage at a time. The guide remains Unverified until a run ID, app revision, dataset revision, and immutable evidence files are published together.

## Evidence identity

??? info "Evidence record"
    - **Status:** Unverified
    - **Source journey:** [moabb-compact-user-journeys-v1](../assets/manifests/moabb-datasets-v1.json)
    - **Source contract SHA-256:** `61097550c8fb6afeb9156c9fbe9207f471eb2d04799cf16672ac4937686a70b9`
    - **MOABB release:** `1.5.0` at `140809d8c48bdf2be953951ff75f688122edee34`
    - **Manifest ID:** Not published
    - **App revision:** Not published
    - **Run ID:** Not published
    - **Dataset revision:** Not published
    - **Evidence files:** None published

!!! warning "Claim boundary"
    The source contract identifies intended inputs and choices, not a completed XBrainLab run. Observed or Bounded status requires a complete identity and immutable evidence files.

## Evidence and limits

### Source and dataset

**Status:** Unverified.

- Planned source files: `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_eeg.eeg`, `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_eeg.vhdr`, `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_eeg.vmrk`, `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_channels.tsv`, `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_events.tsv`.
- Dataset license in the source contract: `CC-BY-4.0`.
- Published XBrainLab run evidence: None.

### Import scope

**Status:** Unverified.

- Open `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_eeg.vhdr` using the `file` route.
- Expected selected EEG files: `lee2021mobile/sub-01/ses-01/eeg/sub-01_ses-01_task-ERP_eeg.vhdr`.
- Published XBrainLab run evidence: None.

### Labels and metadata

**Status:** Unverified.

- Label carrier: `embedded_events`.
- `sub-01_ses-01_task-ERP_eeg.vhdr`: `Stimulus/S  1` = NonTarget, `Stimulus/S  2` = Target.
- Published XBrainLab run evidence: None.

### Preprocess

**Status:** Unverified.

- Planned setting: band-pass `0.5` to `20.0` Hz.
- Published XBrainLab run evidence: None.

### Epoch

**Status:** Unverified.

- Planned window: `-0.25` to `1.0` s; baseline `None`; labels `Target`, `NonTarget`.
- Published XBrainLab run evidence: None.

### Split

**Status:** Unverified.

- Planned split: `0.2` test and `0.2` validation by `trial`; `individual` mode.
- Published XBrainLab run evidence: None.

### Model and training

**Status:** Unverified.

- Planned profile: `EEGNet`, `cpu`, up to `30` epochs, batch `32`, learning rate `0.001`, `adam`.
- Stopping boundary from the source contract: Fixed 30-epoch upper bound with validation-AUC checkpoint selection for the imbalanced ERP task; the held-out test split is not used for stopping.
- Published XBrainLab run evidence: None.

### Evaluation

**Status:** Unverified.

- Planned held-out split: `test`.
- Planned acceptance comparisons: `roc_auc_ovr` > `auc_chance_baseline`; `balanced_accuracy` > `chance_baseline`.
- Read the saved test predictions once, only after the validation-selected checkpoint and fixed epoch budget have completed.
- No measured value is published on this page.
- Published XBrainLab run evidence: None.

### Saliency

**Status:** Unverified.

- Planned methods: `Gradient`, `Gradient * Input`.
- No saliency image is published on this page.
- Published XBrainLab run evidence: None.

### Reproducibility and limitations

**Status:** Unverified.

- Planned seed: `1731`.
- Source contract SHA-256: `61097550c8fb6afeb9156c9fbe9207f471eb2d04799cf16672ac4937686a70b9`.
- One standing training session does not validate walking/running sessions or all 24 subjects.
- The BIDS events table is retained and checksummed but excluded from label application so the journey specifically tests native BrainVision markers.
- P300 quality acceptance deliberately excludes raw accuracy because class imbalance can make a majority-class model look strong.
- Published XBrainLab run evidence: None.
