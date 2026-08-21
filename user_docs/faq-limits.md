# Limits and safety

Use this page to decide whether XBrainLab supports the task you intend to perform. For
an operational problem, see [Troubleshooting](troubleshooting.md).

## Installation and runtime

### Is there a supported installer?

Not yet. XBrainLab is currently run from a source checkout with Poetry. The repository
contains launch support for configured development machines, but no signed,
general-purpose Windows installer.

### Does the Assistant need to be enabled?

No. Import, preprocessing, epoching, training, evaluation, and visualization remain
available through the desktop UI. The Assistant is optional and uses a local model when
enabled.

### Does local processing guarantee privacy?

No. Local execution reduces the need to send EEG data to a cloud service, but privacy
still depends on workstation access, storage permissions, backups, logs, screenshots,
exports, and de-identification. Follow your institution's data-governance rules.

## Data and labels

### Which formats can I import?

The import system recognizes representative GDF, EDF/BDF, EEGLAB SET, BrainVision,
MNE FIF, and BIDS-related sources. External labels can include reviewed MAT and
CSV/TSV/TXT patterns.

Format recognition is not a semantic guarantee. Check events, annotations, units,
class mappings, and metadata in the import review.

### Is XBrainLab a full BIDS validator?

No. XBrainLab can scan a BIDS root, present subject/session/task/run scope, and review
recordings with event carriers. Use a dedicated BIDS validator when dataset compliance
matters.

### Can I import XDF or a live LSL stream?

Not through the current import wizard. A conversion must preserve marker timing and
meaning, and the converted result must still be reviewed before analysis.

### Can I continue without labels?

Yes, when the intended downstream task does not require supervised classes. Supervised
epoching or training is not ready until the event/class meaning is available and
reviewed.

## Analysis boundaries

### Is a training curve a scientific result?

No. It shows optimizer behaviour for the configured partitions. It does not establish
an unbiased test set, cross-subject generalization, statistical significance,
calibration, or physiological validity.

### What does All Folds mean?

Use a combined result only when XBrainLab can establish that the underlying test masks
and cohorts are compatible. Keep the per-fold outputs for review.

### How should I interpret saliency?

Saliency shows model sensitivity for a selected method and input. It is not proof of a
causal or physiological mechanism. Check the trained run, fold, class, input epochs,
channel order, montage, scaling, method stability, and display normalization.

### Can the Assistant make research decisions for me?

No. It can answer questions and request supported actions, but the local model can
misunderstand an instruction. Labels, preprocessing, splits, settings, metrics, and
saliency still require human review.

## Reproducibility

Preserve at least:

- dataset identifier/version and selected file or entity scope;
- import recipe, label source, class map, and confirmation decisions;
- preprocessing and epoch parameters;
- split membership and leakage checks;
- model configuration, seed, environment, and training terminal status;
- evaluation selection and outputs;
- saliency method, source values, and rendering settings;
- the XBrainLab version or source revision and known warnings.

The [Dataset guides](case-studies/index.md) show how to record a bounded route without
claiming that every dataset of the same format behaves identically.
