# Data Import BIDS and Epoch Product Goal

This is a product delivery goal. The previous Data Import checkpoint is not
complete because BIDS was treated as BIDS-like, Review and Import does not yet
teach a beginner what will happen, and Epoch does not fully consume the import
recipe.

## Required Outcome

Deliver a usable Data Import -> Review and Import -> Epoch path for mainstream
EEG datasets, with BIDS-EEG as a first-class supported workflow.

Do not claim generic full-BIDS compliance across all modalities. The target is
XBrainLab BIDS-EEG support:

- BIDS root scan.
- Subject, session, task, run, and datatype discovery.
- Selected scope kept separate from scan location.
- EEG raw file discovery under BIDS layout.
- `participants.tsv` metadata when present.
- `events.tsv` with `onset`, `duration`, `trial_type`, and `value`.
- `events.json` Levels for class names when present.
- `channels.tsv` status / bad-channel handling, or explicit review when
  mismatched.
- BIDS inheritance for events / JSON metadata where practical.
- Multiple subjects, sessions, and runs with clear selection.
- Missing or ambiguous sidecars become structured action items, not silent
  guesses.

## Product Workflow

### 1. Choose EEG Data

- Import BIDS folder must scan as BIDS, not as a generic folder.
- Show a BIDS dataset summary: subjects, sessions, tasks, runs, EEG files,
  events files, and channel sidecars.
- Allow choosing selected scope without changing scan location.

### 2. Load Labels

- For BIDS, labels/events come from `events.tsv` by default.
- External label files still work, but BIDS events must not be treated only as
  generic sidecar labels.

### 3. Review Metadata

- Show subject, session, task, and run from BIDS entities and
  `participants.tsv` where present.
- Preserve user edits in recipe.

### 4. Match Labels

- BIDS mode must expose:
  - label values from `trial_type`, `value`, or the selected label column;
  - class names from `events.json` Levels when available;
  - event timing from `onset` and `duration`;
  - event-code mapping when `value` is present.
- Internal EEG events and external labels must stay separate and must not
  contaminate each other.

### 5. Review and Import

Rebuild this step for beginners. It must answer:

- What EEG files will be imported?
- Where do labels come from?
- Which event / label values become classes?
- What will Epoch use next?
- What is blocked, needs review, or ready?

Do not expose recipe trace as first-layer UX. Keep the primary Apply / Import
action visible.

### 6. Epoch

- Epoch setup must consume import recipe / epoch handoff.
- Imported BIDS events must appear as selectable epoch targets with class names.
- If Data Import chose class labels, Epoch should default to those choices.
- If labels are missing or ambiguous, supervised dataset / training must be
  blocked with an actionable reason.
- Add tests for BIDS import -> epoch creation.

## Required Subagent Gates

Use subagents as hard gates. Do not complete until all gates pass.

1. UI Product Gate
   - Reviews screenshots and beginner usability.
   - Must specifically approve Review and Import.

2. Mainstream Data Format Gate
   - Verifies GDF / internal events, MAT labels, CSV / TSV labels, and generic
     EEG events still work.

3. BIDS Completion Gate
   - Verifies BIDS-EEG support is real, not BIDS-like wording.
   - Checks BIDS scan, sidecars, inheritance, `events.json` Levels,
     `channels.tsv`, selected scope, and recipe replay.

4. Epoch Integration Gate
   - Verifies Data Import decisions drive Epoch defaults and blockers.
   - Checks imported class labels / events survive into epoch creation and
     downstream readiness.

## Validation Requirements

Required tests:

- BIDS root scan with multiple subjects, sessions, and runs.
- Selected scope vs scan location for BIDS.
- `events.tsv` onset / duration / `trial_type` / `value` parsing.
- `events.json` Levels -> class map.
- BIDS inheritance for events metadata, or explicit documented limitation with
  blocker.
- `channels.tsv` bad / status handling, or explicit review item.
- Missing `events.tsv`: raw import allowed, supervised workflow blocked.
- Malformed `events.tsv` missing onset: blocked.
- BIDS import -> Review and Import -> Apply -> Epoch creates expected epochs.
- Recipe save / reload preserves BIDS choices and epoch handoff.
- External labels do not contaminate BIDS / internal event choices.

Required artifacts:

- Full screenshots for all Data Import steps in BIDS mode.
- Review and Import ready / needs review / blocked screenshots.
- Epoch screen after BIDS import.
- JSON evidence showing recipe and epoch handoff from real backend output.

Required validation commands:

- Focused backend Data Interpretation tests.
- Focused Epoch tests.
- Focused UI / dialog tests.
- Product smoke: Import BIDS folder -> Review Metadata -> Match Labels ->
  Review and Import -> Apply -> Create Epoch.
- `ruff check` and `ruff format --check`.
- `basedpyright`.
- `mkdocs build --strict`.
- Architecture compliance.

Commit and push the branch after passing all gates.
