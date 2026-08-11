---
hide:
  - navigation
---

# Limits and FAQ

<p class="page-kicker">Current development-build boundaries</p>

<p class="portal-lede">Use these limits when deciding whether a dataset, workflow,
result, or local setup is ready to continue. A dataset route becomes published evidence
only when its identity block provides the dataset revision, app revision, run ID, and
evidence files together.</p>

<div class="status-strip status-strip--compact boundary-strip" markdown>
  <div><span class="status-label">Published manual runs</span><strong>None</strong></div>
  <div><span class="status-label">Distribution</span><strong>No signed general-purpose installer</strong></div>
  <div><span class="status-label">Explicit import boundary</span><strong>No XDF or live LSL stream</strong></div>
</div>

<nav class="page-jumps" aria-label="FAQ sections" markdown>
[Data and import](#data-and-import) · [Workflow decisions](#workflow-decisions) ·
[Runtime and privacy](#runtime-and-privacy) · [Current claim boundary](#current-claim-boundary)
</nav>

## Data and import

### Which manual dataset runs are published here?

None currently meet the user-site identity contract. Two scoped manual run guides are
available:

- Graz / BCI Competition IV 2a: `A01T`, `A02T`, `A03T` with matching MAT labels.
- OpenNeuro `ds003061`: `sub-001`, session `01`, task `P300`, runs `1`–`3`.

Both pages are marked **Unverified**. Their exact scopes are instructions and stop
conditions, not claims of a complete manual run through saliency.

Three additional MOABB execution guides cover Ofner2017, PhysionetMI, and
Lee2021Mobile ERP. They are generated from a versioned source contract and provide
exact selected inputs, choices, checkpoints, and limitations. They are marked
**Execution pending / Unverified** until an identified XBrainLab run supplies evidence.

### Which EEG formats can I try?

The import system recognizes representative GDF, EDF/BDF, EEGLAB SET, BrainVision,
MNE FIF, and BIDS-related sources. External label carriers can include MAT and reviewed
CSV/TSV/TXT patterns.

Support remains semantics-dependent. A familiar extension does not establish that its
events, annotations, time units, class map, sidecars, or metadata will be interpreted
correctly. Always use the import preview and stop when the required meaning is unclear.

### Is XBrainLab a full BIDS validator?

No. The interface can scan a BIDS root, summarize subject/session/task/run scope, pair
recordings with event carriers, and present metadata for review. It does not certify
full BIDS compliance or arbitrary inheritance/sidecar behavior.

Use a dedicated BIDS validator as part of dataset quality control.

### Can I import XDF or a live LSL stream?

Not through the current import wizard. XDF/LSL stream selection is an explicit blocked
boundary. Convert the data through a controlled, documented process to a reviewed EEG
format, and preserve marker/time semantics during conversion.

### Can I continue without labels?

The import workflow can continue without labels when the intended downstream task does
not require supervised classes. Supervised epoching, dataset generation, or training
cannot be considered ready until event/class semantics are available and reviewed.

### Why do I need to review metadata?

Subject, session, task, and run identity determine what can be split or compared. A
trial-level split can look numerically strong while leaking subject- or session-specific
information. Preserve metadata early so the split can match the research question.

## Workflow decisions

### Why is an action disabled?

The workflow is dependency ordered. Common reasons include:

- no reviewed import is active;
- labels or metadata need a decision;
- epochs do not exist;
- dataset, split, model, or training settings are incomplete;
- no compatible trained result exists for evaluation or saliency;
- an upstream resource is locked by a downstream stage or running job.

Read the visible empty/blocked message first. Use reset or a new session when changing an
earlier decision would invalidate existing epochs, datasets, or results.

### Can I treat a training curve as a scientific result?

No. A training curve shows optimizer behavior on the configured partitions. It does not
by itself establish an unbiased test set, cross-subject generalization, statistical
significance, calibration, or physiological validity.

Every reported result should be traceable to source scope, labels, preprocessing,
epochs, split membership, model settings, random seeds, software revision, and held-out
cohort.

### What does an All Folds result mean?

Use an aggregate only when the underlying folds represent compatible test masks and
cohorts. Keep fold-level outputs. Do not average values merely because every run has a
field with the same name.

### How should I interpret saliency?

Saliency describes model sensitivity under a selected method and input. It is not proof
of a causal or physiological mechanism. Check the trained run, fold, class, input
epochs, scaling, channel order, montage, method stability, and display normalization.

## Runtime and privacy

### Does the assistant need to be available?

No. The desktop workflow is the primary product and remains usable without the
assistant. The assistant uses a local-only model runtime when configured, but it is
still a prototype boundary and must not replace review of labels, splits, settings, or
results.

### Does local processing guarantee privacy?

Local execution reduces the need to send EEG data to a cloud service, but privacy still
depends on workstation access, storage permissions, backups, logs, exports, and how
datasets are de-identified. Follow your institution's data governance requirements.

Do not place identifying participant information into screenshots or shared recipes.

### Is there a supported installer?

Not yet. The repository contains a development launcher for a configured Windows/WSL
machine, but there is no signed, general-purpose installer or completed first-run
experience. Follow [Getting Started](getting-started.md) for the current source-based
setup.

### What should I preserve for reproducibility?

At minimum:

- dataset identifier/version and selected file/entity scope;
- import recipe, label carriers, class map, and confirmation decisions;
- preprocessing and epoch parameters;
- split memberships and leakage checks;
- model configuration, random seeds, and environment identity;
- training history and terminal status;
- evaluation selection and outputs;
- saliency selection, source values, and rendering settings;
- XBrainLab revision and known warnings.

The [case-study structure](case-studies/index.md) is a practical checklist for this
record.

## Current claim boundary

XBrainLab can be described as a local EEG desktop workflow under active development.
It must not currently be described as:

- a released or signed clinical/research product;
- compatible with every file carrying a recognized extension;
- a full BIDS validator;
- validated for arbitrary P300, SSVEP, clinical, XDF/LSL, MOABB, or proprietary data;
- an automatic source of publication-ready metrics;
- scientifically validated because a pipeline or UI walkthrough passed;
- assistant-ready for unsupervised research decisions.
