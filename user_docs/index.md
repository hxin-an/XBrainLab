# XBrainLab User Guide

XBrainLab is a local desktop application for preparing EEG data, training a model, and
reviewing evaluation and saliency results. The application keeps the analysis on your
machine; the optional Assistant uses the same workflow controls as the desktop UI.

!!! info "Current distribution"
    XBrainLab is currently distributed as a source-based desktop application. There is
    no signed installer. Follow [Getting started](getting-started.md) to install and run
    the application from a repository checkout.

## Start here

- **First time using XBrainLab?** Install the application and complete one reviewed
  import in [Getting started](getting-started.md).
- **Already have a dataset loaded?** Follow the stage-by-stage checks in
  [Run an EEG workflow](workflow.md).
- **Want to use the local Assistant?** Read [Use the Assistant](assistant.md) before
  enabling the model runtime.
- **Something is blocked or unavailable?** Start with
  [Troubleshooting](troubleshooting.md).
- **Working with a known public dataset?** Choose a scoped example from the
  [Dataset guides](case-studies/index.md).

## Workflow at a glance

| Stage | What you decide | What to check before continuing |
| --- | --- | --- |
| Import | Which recordings, labels, and metadata belong to this analysis | Selected files, event meanings, subject/session/run identity |
| Preprocess | Which signal operations are appropriate | Sampling rate, channel types, preview, operation history |
| Epoch | Which event and time window define a trial | Anchor event, timing, class counts, rejected boundaries |
| Split | What must remain independent | Subject/session/run grouping and leakage risk |
| Train | Which model and settings define the run | Dataset, split, model, resources, terminal status |
| Evaluate | Which fold, run, and split a result describes | Selection identity and compatible test masks |
| Visualize | Which trained run and input a saliency view uses | Method, class, channel order, source values |

XBrainLab can execute this workflow, but it cannot decide whether a preprocessing
choice, split, metric, or saliency interpretation is scientifically appropriate for
your study. Keep the protocol and analysis decisions with the run record.

## What the guide does not claim

Recognizing a file format does not guarantee that arbitrary files of that format have
correct event or label semantics. A successful training run does not establish an
unbiased scientific result. See [Limits and safety](faq-limits.md) before using an
output in a report or publication.

[Open Getting started](getting-started.md){ .md-button .md-button--primary }

Project status, architecture, and validation contracts are maintained in the
<a href="../">engineering documentation</a>.
