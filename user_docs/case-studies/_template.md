---
case_id: "{{CASE_ID}}"
evidence_record: "case-studies/manifests/{{CASE_ID}}.yml"
publication_status: unverified
---

# {{DATASET_NAME}}: {{SOURCE_DESCRIPTION}}

<!--
Create the matching evidence record from manifests/_manifest-template.yml. Publication
status may only be promoted by the evidence publisher. Page identity, stage status, and
the manifest must agree; unavailable stages stay visible and must not borrow evidence
from another run.
-->

| | This guide uses |
| --- | --- |
| Paradigm | {{PARADIGM}} |
| Scope | {{EXACT_SCOPE}} |
| Files | {{SOURCE_PATTERN}} |
| Published run | Unverified |

{{CASE_BOUNDARY_SUMMARY}}

## Run this dataset

### Source and version

{{SOURCE_AND_VERSION_INSTRUCTIONS}}

### App action

{{APP_ACTIONS}}

### Choices

{{DATASET_CHOICES}}

### Expected checkpoint

{{EXPECTED_CHECKPOINT}}

### Stop condition

{{STOP_CONDITION}}

### Next step

{{NEXT_STEP_WITH_LAST_VERIFIED_BOUNDARY}}

## Evidence identity

??? info "Why this guide is marked Unverified"
    | Identity field | Published value |
    | --- | --- |
    | Manifest ID | Not published |
    | App revision | Not published |
    | Run ID | Not published |
    | Dataset revision | Not published |
    | Evidence files | None published |

{{WHY_IDENTITY_IS_OR_IS_NOT_PUBLISHABLE}}

## Evidence and limits

### Source and dataset

**Status:** Unverified. {{SOURCE_STAGE_BOUNDARY}}

### Import scope

**Status:** Unverified. {{IMPORT_SCOPE_STAGE_BOUNDARY}}

### Labels and metadata

**Status:** Unverified. {{LABEL_METADATA_STAGE_BOUNDARY}}

### Preprocess

**Status:** Unverified. {{PREPROCESS_STAGE_BOUNDARY}}

### Epoch

**Status:** Unverified. {{EPOCH_STAGE_BOUNDARY}}

### Split

**Status:** Unverified. {{SPLIT_STAGE_BOUNDARY}}

### Model and training

**Status:** Unverified. {{TRAINING_STAGE_BOUNDARY}}

### Evaluation

**Status:** Unverified. {{EVALUATION_STAGE_BOUNDARY}}

{{BOUNDED_OBSERVED_METRICS_TABLE}}

### Saliency

**Status:** Unverified. {{SALIENCY_STAGE_BOUNDARY}}

{{IMMUTABLE_SALIENCY_SCREENSHOT}}

### Reproducibility and limitations

**Status:** Unverified. {{REPRODUCIBILITY_STAGE_BOUNDARY}}

{{OBSERVED_RUN_LIMITATIONS}}
