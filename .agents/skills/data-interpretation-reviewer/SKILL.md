---
name: data-interpretation-reviewer
description: "Use for XBrainLab EEG import, event/label semantics, BIDS, metadata, recipe trace, dataset capability, and custom fallback. Do not use for generic file IO."
---

# Data Interpretation Reviewer

Review how raw files become a bounded, explainable EEG workflow.

## Workflow

1. Identify the dataset source, selected recordings, format, event/label carriers, and intended task.
2. Read the relevant data architecture/target section and the specific importer or service.
3. Trace scan, preview, validation, apply, recipe publication, and downstream readiness.
4. Distinguish observed metadata from inference, recommendation, and explicit user choice.
5. Check subject/session/run scoping, sampling-frequency compatibility, event placement, duration,
   class exclusion, missing labels, and mixed-source failure behavior.
6. Verify failures are recoverable and do not partially mutate authoritative state.
7. Require source-diverse evidence for broad support claims.

## Boundaries

- A file extension is format coverage, not dataset-family certification.
- BIDS hints must come from bounded selected-run evidence; uncertainty requires review.
- Excluding an event from supervised classes must not silently delete source evidence.
- Custom fallback must preserve provenance and must not masquerade as native support.
- Recipe and state publication must record the inputs and choices needed to reproduce the result.

## Output

Report supported path, ambiguity/failure cases, state/provenance risks, missing dataset evidence,
recommended tests, and claims that remain out of scope.
