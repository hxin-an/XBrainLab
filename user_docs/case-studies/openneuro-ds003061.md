---
case_id: openneuro-ds003061
evidence_record: case-studies/manifests/openneuro-ds003061.yml
publication_status: unverified
---

# OpenNeuro ds003061: P300 BIDS

| | This guide uses |
| --- | --- |
| Paradigm | Auditory P300 |
| Scope | `sub-001`, session `01`, task `P300`, runs `1`–`3` |
| Files | One EEGLAB SET recording and one `events.tsv` per run |
| Published run | Unverified |

Use this page to review one subject and three runs. It does not prescribe a class
column, P300 analysis settings, or a verified downstream workflow.

## Run this dataset

### Source and version

- OpenNeuro dataset `ds003061`.
- Select `sub-001`, session `01`, task `P300`, runs `1`, `2`, and `3`.
- Record the OpenNeuro snapshot before import; this page does not publish a pinned
  dataset revision or file hashes.

### App action

1. Open **Dataset** and choose **Import BIDS**.
2. Select the dataset root.
3. In the subject selector, check only `sub-001`.
4. Continue to the import review and inspect the selected entities and event carriers.

### Choices

- Keep only `sub-001` selected.
- Confirm session `01`, task `P300`, and runs `1`, `2`, and `3`.
- Pair each SET recording with the `events.tsv` from the same run.
- Choose a class column only after checking the dataset documentation; this guide does
  not supply one.

### Expected checkpoint

- Selected subjects: `sub-001` only.
- Selected scope: one subject and three EEG files.
- Entities: session `01`, task `P300`, runs `1`, `2`, `3`.
- Labels: one run-matched `events.tsv` for each selected recording.

### Stop condition

Stop if another subject enters the scope, one of the three runs is missing, a SET file
cannot be paired with its event carrier, entity values differ, or the class column
cannot be justified from the dataset documentation.

### Next step

Continue through **Review and Import** only after the scope matches. Select all later
settings from the study protocol; this page does not validate them.

## Evidence identity

??? info "Why this guide is marked Unverified"
    | Identity field | Published value |
    | --- | --- |
    | Manifest ID | Not published |
    | App revision | Not published |
    | Run ID | Not published |
    | Dataset revision | Not published |
    | Evidence files | None published |

    No event count or performance value is promoted without a complete identity.

## Evidence and limits

### Source and dataset

**Status:** Unverified. The dataset and scenario are named, but no snapshot or file
hashes are published here.

### Import scope

**Status:** Unverified. The subject and runs are specified but no identified run is
published.

### Labels and metadata

**Status:** Unverified. Event-carrier pairing is an instruction; no class map or imported
alignment is published.

### Preprocess

**Status:** Unverified. No dataset-specific preprocessing sequence is published.

### Epoch

**Status:** Unverified. No event window, baseline, rejection policy, or distribution is
published.

### Split

**Status:** Unverified. No run-, session-, or subject-level split is published.

### Model and training

**Status:** Unverified. No model, settings, seed, or terminal training run is published.

### Evaluation

**Status:** Unverified. No held-out metric or confusion matrix is published.

### Saliency

**Status:** Unverified. No run-bound saliency result is published.

### Reproducibility and limitations

**Status:** Unverified. This guide does not establish full BIDS validation, compatibility
with arbitrary P300 data, model generalization, or physiological interpretation.

[Return to Dataset guides](index.md)
