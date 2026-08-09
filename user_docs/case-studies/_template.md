---
case_id: "{{CASE_ID}}"
evidence_record: "case-studies/manifests/{{CASE_ID}}.yml"
publication_status: unverified
---

# {{DATASET_NAME}}: {{SOURCE_DESCRIPTION}}

<!--
Publication contract:
- Create the matching evidence record from manifests/_manifest-template.yml.
- Keep publication_status and every stage unverified until the publication CLI accepts
  one exact showcase Qt capture manifest.
- Do not promote a page by editing front matter or evidence records. The publisher requires
  clean source identity, the exact registry digest and source checksums, a successful
  load-through-saliency command trace, accepted held-out metrics, and immutable files.
- Bounded publication requires manifest_id, app_revision, run_id, dataset_revision,
  content-addressed evidence files, and a hash-checked publication receipt.
- Page front matter, evidence identity, stage badges, and manifest status must agree.
- Keep unavailable stages in the page; never fill them from another dataset or run.
-->

<div class="case-summary" markdown>
  <div><span>Paradigm</span><strong>{{PARADIGM}}</strong></div>
  <div><span>Route scope</span><strong>{{EXACT_SCOPE}}</strong></div>
  <div><span>Source pattern</span><strong>{{SOURCE_PATTERN}}</strong></div>
  <div><span>Published evidence</span><strong>Unverified</strong></div>
</div>

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

<div class="evidence-identity evidence-identity--unverified" markdown>
  <span class="evidence-badge evidence-badge--unverified">Unverified</span>

  | Identity field | Published value |
  | --- | --- |
  | Manifest ID | Not published |
  | App revision | Not published |
  | Run ID | Not published |
  | Dataset revision | Not published |
  | Evidence files | None published |
</div>

{{WHY_IDENTITY_IS_OR_IS_NOT_PUBLISHABLE}}

## Evidence and limits

### Source and dataset

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

{{SOURCE_STAGE_BOUNDARY}}

### Import scope

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

{{IMPORT_SCOPE_STAGE_BOUNDARY}}

### Labels and metadata

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

{{LABEL_METADATA_STAGE_BOUNDARY}}

### Preprocess

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

{{PREPROCESS_STAGE_BOUNDARY}}

### Epoch

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

{{EPOCH_STAGE_BOUNDARY}}

### Split

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

{{SPLIT_STAGE_BOUNDARY}}

### Model and training

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

{{TRAINING_STAGE_BOUNDARY}}

### Evaluation

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

{{EVALUATION_STAGE_BOUNDARY}}

{{BOUNDED_OBSERVED_METRICS_TABLE}}

### Saliency

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

{{SALIENCY_STAGE_BOUNDARY}}

{{IMMUTABLE_SALIENCY_SCREENSHOT}}

### Reproducibility and limitations

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

{{REPRODUCIBILITY_STAGE_BOUNDARY}}

{{OBSERVED_RUN_LIMITATIONS}}
