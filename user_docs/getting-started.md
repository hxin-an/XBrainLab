# Getting started

This guide takes you from a source checkout to a reviewed EEG import. You do not need
the local Assistant to use the EEG workflow.

## Before you begin

You need:

- Python 3.11 or 3.12;
- Poetry;
- enough local storage for the Python environment and your EEG data;
- recordings you are permitted to process;
- protocol notes or label files when event meanings are not embedded in the recording.

The current project does not provide a signed Windows installer.

## 1. Install the environment

From the repository root:

```bash
poetry install
```

Install the optional local Assistant runtime only if you plan to use it:

```bash
poetry install --with llm
```

## 2. Launch XBrainLab

```bash
poetry run python run.py
```

The main window should open on **Dataset** and show these top-level areas:

`Dataset` · `Preprocess` · `Training` · `Evaluation` · `Visualization`

If the window does not open, see [XBrainLab does not start](troubleshooting.md#xbrainlab-does-not-start).

## 3. Choose a small first dataset

Start with one subject or a few runs whose protocol you understand. Before importing,
identify:

- whether labels come from events, annotations, or separate files;
- which values represent analysis classes;
- which subject, session, task, and run fields must survive into the split;
- whether the source should remain read-only.

Do not use an unfamiliar large dataset as the first setup check.

## 4. Open the correct import route

In **Dataset**, choose the action that matches the source:

| Source | Action |
| --- | --- |
| One recording | **Import file** |
| Several recordings in a normal folder | **Import folder** |
| A BIDS dataset root | **Import BIDS** |
| A saved reviewed import | **Reload recipe** |

The import review walks through five tasks:

1. **Choose EEG Data** — confirm the selected files or BIDS entities.
2. **Load Labels** — use discovered labels, add a label source, or continue without
   labels when the intended task allows it.
3. **Review Metadata** — inspect subject, session, task, and run identity.
4. **Match Labels** — confirm how rows or event codes map to the recordings.
5. **Review and Import** — resolve blocked items before applying the import.

## 5. Check the imported session

After import, read **Data Summary** before opening Preprocess:

- the recording count matches the selected scope;
- subject/session/task/run values match the study;
- event and class counts are plausible;
- channel count and sampling rate match the acquisition;
- every warning is understood.

If any of these values are wrong, fix the import before preprocessing. Once epochs or a
training plan exist, reset the workflow deliberately instead of replacing upstream data
inside the same run.

Next: [Run an EEG workflow](workflow.md).
