---
title: PhysionetMI Run Semantics
case_id: moabb-physionetmi
evidence_record: case-studies/manifests/moabb-physionetmi.yml
publication_status: unverified
generated_from: moabb-datasets-v1
---

# PhysionetMI Run Semantics

<div class="case-summary" markdown>
  <div><span>Paradigm</span><strong>motor_imagery</strong></div>
  <div><span>Route scope</span><strong>Subject(s) 1; session(s) 0; run(s) 4, 6, 8, 10, 12, 14; EDF+ source</strong></div>
  <div><span>Source format</span><strong>EDF+</strong></div>
  <div><span>Published evidence</span><strong>Unverified</strong></div>
</div>

<span class="evidence-badge evidence-badge--unverified">Unverified</span> <span class="scope-label">Execution pending</span>

This is a manifest-generated execution guide. It contains no completed XBrainLab run, metric, or saliency claim.

## Run this dataset

Follow the route only while each checkpoint matches. The values below come from the linked source contract; they are planned inputs, not observed results.

### Source and version

- Dataset: [EEG Motor Movement/Imagery Dataset](https://physionet.org/content/eegmmidb/1.0.0/).
- Dataset DOI: [doi:10.13026/C28G6P](https://doi.org/10.13026/C28G6P).
- Repository and license: PhysioNet, `ODC-By-1.0`.
- MOABB adapter: [version 1.5.0 at 140809d8c48b](https://github.com/NeuroTechX/moabb/blob/140809d8c48bdf2be953951ff75f688122edee34/moabb/datasets/physionet_mi.py); [dataset reference](https://moabb.neurotechx.com/docs/generated/moabb.datasets.PhysionetMI.html).
- Site source contract: [moabb-compact-user-journeys-v1](../assets/manifests/moabb-datasets-v1.json), SHA-256 `61097550c8fb6afeb9156c9fbe9207f471eb2d04799cf16672ac4937686a70b9`.

- `physionetmi/sub-001/S001R04.edf`: `sha256` `3d161f88e1c00632585287d2ce584c2bc0f08862438eb255ea8723e00fac693d` ([source](https://physionet.org/files/eegmmidb/1.0.0/S001/S001R04.edf))
- `physionetmi/sub-001/S001R06.edf`: `sha256` `5369364f2c4e81ca141679d6dd2ba6ece61c7eb53d7fae31241b308876e1b6b3` ([source](https://physionet.org/files/eegmmidb/1.0.0/S001/S001R06.edf))
- `physionetmi/sub-001/S001R08.edf`: `sha256` `358fb5189220725141968ae285fbe9e3f36210b834ffba71d940af308e3aca68` ([source](https://physionet.org/files/eegmmidb/1.0.0/S001/S001R08.edf))
- `physionetmi/sub-001/S001R10.edf`: `sha256` `20de1c7746c2349d16bda5e9f1b0ac7b7ad1581102a2e30dd2ac422696f62fb1` ([source](https://physionet.org/files/eegmmidb/1.0.0/S001/S001R10.edf))
- `physionetmi/sub-001/S001R12.edf`: `sha256` `2b281c9b687b4c4176e83251d74743721f2d6ebd76656a972a3b9c44d9d88cd5` ([source](https://physionet.org/files/eegmmidb/1.0.0/S001/S001R12.edf))
- `physionetmi/sub-001/S001R14.edf`: `sha256` `2110c48e3106898e3dbca47e39b330637afd3d3b8bc2da3ba1e44f4ac1118137` ([source](https://physionet.org/files/eegmmidb/1.0.0/S001/S001R14.edf))

### App action

1. Obtain only the files listed above and verify every checksum before opening the app.
2. Start the XBrainLab development build and choose **Load Data**.
3. Use the **folder** route and select `physionetmi/sub-001`.
4. Keep the import review open until the selected files and labels match this page.

### Choices

- Use `embedded_events` as the label carrier.
- `S001R04.edf`: `T1` = left fist, `T2` = right fist.
- `S001R06.edf`: `T1` = both fists, `T2` = both feet.
- `S001R08.edf`: `T1` = left fist, `T2` = right fist.
- `S001R10.edf`: `T1` = both fists, `T2` = both feet.
- `S001R12.edf`: `T1` = left fist, `T2` = right fist.
- `S001R14.edf`: `T1` = both fists, `T2` = both feet.
- Preprocess: band-pass `4.0` to `38.0` Hz.
- Epoch: `0.0` to `2.0` s, baseline `None`.
- Split: `0.2` test and `0.2` validation by `trial`; `individual` training.
- Planned training: `EEGNet` on `cpu`, up to `30` epochs, batch `8`, learning rate `0.001`, checkpoint choice `val_acc`.

### Expected checkpoint

- Selected EEG files: `physionetmi/sub-001/S001R04.edf`, `physionetmi/sub-001/S001R06.edf`, `physionetmi/sub-001/S001R08.edf`, `physionetmi/sub-001/S001R10.edf`, `physionetmi/sub-001/S001R12.edf`, `physionetmi/sub-001/S001R14.edf`.
- Resolved labels: `T1`, `T2`.
- Status: pending visual confirmation in an identified XBrainLab run.

### Stop condition

Stop before preprocessing if a checksum differs, the selected file set changes, a run-specific label maps differently, or the app does not expose the stated choice. Do not substitute values or interpret later output as evidence for this route.

### Next step

After the import checkpoint matches, apply the planned settings one stage at a time and capture a run ID, app revision, dataset revision, and immutable evidence files. Until those fields are published below, every stage remains pending and Unverified.

## Evidence identity

<div class="evidence-identity" markdown>
<p><strong>Evidence state</strong><br>Unverified</p>
<p><strong>Source journey</strong><br>[moabb-compact-user-journeys-v1](../assets/manifests/moabb-datasets-v1.json)</p>
<p><strong>Source contract SHA-256</strong><br>`61097550c8fb6afeb9156c9fbe9207f471eb2d04799cf16672ac4937686a70b9`</p>
<p><strong>MOABB release</strong><br>`1.5.0` at `140809d8c48bdf2be953951ff75f688122edee34`</p>
<p><strong>Manifest ID</strong><br>Not published</p>
<p><strong>App revision</strong><br>Not published</p>
<p><strong>Run ID</strong><br>Not published</p>
<p><strong>Dataset revision</strong><br>Not published</p>
<p><strong>Evidence files</strong><br>None published</p>
</div>

!!! warning "Claim boundary"
    The linked journey manifest identifies intended inputs and choices. It does not identify a completed XBrainLab run. Observed or Bounded status requires all identity fields and evidence files above.

## Evidence and limits

### Source and dataset

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

- Planned source files: `physionetmi/sub-001/S001R04.edf`, `physionetmi/sub-001/S001R06.edf`, `physionetmi/sub-001/S001R08.edf`, `physionetmi/sub-001/S001R10.edf`, `physionetmi/sub-001/S001R12.edf`, `physionetmi/sub-001/S001R14.edf`.
- Dataset license in the source contract: `ODC-By-1.0`.
- Published XBrainLab run evidence: None.

### Import scope

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

- Open `physionetmi/sub-001` using the `folder` route.
- Expected selected EEG files: `physionetmi/sub-001/S001R04.edf`, `physionetmi/sub-001/S001R06.edf`, `physionetmi/sub-001/S001R08.edf`, `physionetmi/sub-001/S001R10.edf`, `physionetmi/sub-001/S001R12.edf`, `physionetmi/sub-001/S001R14.edf`.
- Published XBrainLab run evidence: None.

### Labels and metadata

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

- Label carrier: `embedded_events`.
- `S001R04.edf`: `T1` = left fist, `T2` = right fist.
- `S001R06.edf`: `T1` = both fists, `T2` = both feet.
- `S001R08.edf`: `T1` = left fist, `T2` = right fist.
- `S001R10.edf`: `T1` = both fists, `T2` = both feet.
- `S001R12.edf`: `T1` = left fist, `T2` = right fist.
- `S001R14.edf`: `T1` = both fists, `T2` = both feet.
- Published XBrainLab run evidence: None.

### Preprocess

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

- Planned setting: band-pass `4.0` to `38.0` Hz.
- Published XBrainLab run evidence: None.

### Epoch

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

- Planned window: `0.0` to `2.0` s; baseline `None`; labels `T1`, `T2`.
- Published XBrainLab run evidence: None.

### Split

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

- Planned split: `0.2` test and `0.2` validation by `trial`; `individual` mode.
- Published XBrainLab run evidence: None.

### Model and training

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

- Planned profile: `EEGNet`, `cpu`, up to `30` epochs, batch `8`, learning rate `0.001`, `adam`.
- Stopping boundary from the source contract: Fixed 30-epoch upper bound with validation-accuracy checkpoint selection; the held-out test split is not used for stopping.
- Published XBrainLab run evidence: None.

### Evaluation

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

- Planned held-out split: `test`.
- Planned acceptance comparisons: `balanced_accuracy` > `chance_baseline`; `accuracy` > `majority_baseline`.
- Read the saved test predictions once, only after the validation-selected checkpoint and fixed epoch budget have completed.
- No measured value is published on this page.
- Published XBrainLab run evidence: None.

### Saliency

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

- Planned methods: `Gradient`, `Gradient * Input`.
- No saliency image is published on this page.
- Published XBrainLab run evidence: None.

### Reproducibility and limitations

<span class="evidence-badge evidence-badge--unverified">Unverified</span>

- Planned seed: `1730`.
- Source contract SHA-256: `61097550c8fb6afeb9156c9fbe9207f471eb2d04799cf16672ac4937686a70b9`.
- Six imagery runs from one subject test repeated run-dependent annotation semantics and within-subject quality, not population performance.
- T0 rest annotations are deliberately excluded from the supervised classes.
- Published XBrainLab run evidence: None.
