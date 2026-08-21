---
case_id: graz-2a
evidence_record: case-studies/manifests/graz-2a.yml
publication_status: unverified
---

# Graz 2a: GDF recordings with MAT labels

| | This guide uses |
| --- | --- |
| Paradigm | Motor imagery |
| Scope | `A01T`, `A02T`, `A03T` |
| Files | Three GDF recordings and three matching MAT label files |
| Published run | Unverified |

Use this page to review one three-subject import. It does not prescribe or verify the
later preprocessing, training, evaluation, or saliency stages.

## Run this dataset

### Source and version

- BCI Competition IV Dataset 2a training recordings.
- Select `A01T.gdf`, `A02T.gdf`, and `A03T.gdf` with the corresponding MAT files.
- Record the dataset source and hash all six files; this page does not publish a pinned
  dataset revision.

### App action

1. Open **Dataset** and choose **Import folder**.
2. Keep only the three GDF recordings listed above.
3. In **Load Labels**, add the folder containing the three MAT files.
4. Continue to **Match Labels**, but do not confirm the import until the checks below
   match.

### Choices

- Pair each MAT file with the GDF file that has the same subject stem.
- Review **EEG event order** against cue codes `769`, `770`, `771`, and `772`.
- Do not treat every event in the GDF as a class event.
- Confirm subject/session meaning from the dataset documentation rather than relying on
  the filename alone.

### Expected checkpoint

- EEG data: `A01T.gdf`, `A02T.gdf`, `A03T.gdf`.
- Labels: one MAT file paired with each recording.
- Placement: class labels aligned to the reviewed cue events.
- **Review and Import** has no unexplained blocker.

### Stop condition

Stop before **Confirm and Import** if a file is missing, a MAT file pairs with the wrong
subject, cue events are absent, counts are implausible, or the metadata cannot be
explained from the dataset documentation.

### Next step

Confirm the import only after the checkpoint matches, then open **Preprocess**. Choose
all later settings from the study protocol; this guide does not validate them.

## Evidence identity

??? info "Why this guide is marked Unverified"
    | Identity field | Published value |
    | --- | --- |
    | Manifest ID | Not published |
    | App revision | Not published |
    | Run ID | Not published |
    | Dataset revision | Not published |
    | Evidence files | None published |

    A future publication must bind these values in one record before any stage can be
    promoted beyond **Unverified**.

## Evidence and limits

### Source and dataset

**Status:** Unverified. The source is named, but no pinned revision or hashes are
published here.

### Import scope

**Status:** Unverified. The three-recording route is specified but no identified run is
published.

### Labels and metadata

**Status:** Unverified. Pairing and cue checks are instructions, not observed alignment
evidence.

### Preprocess

**Status:** Unverified. No operation sequence or before/after review is published.

### Epoch

**Status:** Unverified. No event window, baseline, rejection policy, or class count is
published.

### Split

**Status:** Unverified. No competition-, subject-, session-, or trial-level split is
published.

### Model and training

**Status:** Unverified. No model, settings, seed, or terminal training run is published.

### Evaluation

**Status:** Unverified. No held-out metric or confusion matrix is published.

### Saliency

**Status:** Unverified. No run-bound saliency result is published.

### Reproducibility and limitations

**Status:** Unverified. This guide does not establish compatibility with every GDF/MAT
schema, model generalization, or physiological interpretation.

[Return to Dataset guides](index.md)
