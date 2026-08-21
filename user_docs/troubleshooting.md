# Troubleshooting

Start with what is visible in the application. A disabled action, empty panel, warning,
or terminal message usually identifies the missing prerequisite.

## XBrainLab does not start

From the repository root, verify that the managed environment exists and launch through
Poetry:

```bash
poetry install
poetry run python run.py
```

If installation fails, keep the complete terminal output and check the supported Python
version. Do not delete datasets or model caches as a first troubleshooting step.

## Import cannot be confirmed

Review the blocked row in the import dialog. Common causes include:

- no EEG recording is selected;
- an external label file cannot be matched to a recording;
- the label placement or class source still needs a choice;
- required metadata is missing for the selected downstream task;
- the selected scope exceeds the available resources.

Return to the indicated import step. Do not choose a label mapping only to enable the
button; confirm it from the dataset protocol.

## An action is disabled

| Action area | Check first |
| --- | --- |
| Preprocess | A reviewed import is active |
| Epoch | Reviewed events or labels exist |
| Dataset split | Epochs and required grouping metadata exist |
| Start Training | Split, model, settings, and resources are ready |
| Evaluation | A compatible completed training result is selected |
| Compute Saliency | A compatible trained model, input, and method are selected |

An upstream stage may also be locked while downstream data or a background job owns it.
Stop the job or reset from the earliest stage that needs to change.

## Training stops or fails

Read the terminal status and resource message. Check the input shape, model
compatibility, batch size, device selection, and available memory. A failed run should
remain identifiable in history; do not describe it as completed because partial curves
exist.

If resources are insufficient, change the configuration explicitly. Do not assume that
XBrainLab silently selected a smaller model or different device.

## Evaluation or Visualization is empty

Confirm the selected fold, run, split, class, and input. Empty selectors or panels often
mean that no compatible completed result is available for the current workflow state.

For saliency, verify that the chosen model supports the required gradient operation and
wait for the matching computation to finish.

## Assistant is unavailable or stays busy

Check the status shown in the Assistant:

- **Loading** — wait for the selected local model to finish loading.
- **Unavailable/Failed** — review the model configuration, cache, and resource message.
- **Waiting for confirmation** — approve or cancel the visible request.
- **Waiting for a dialog** — complete or cancel the desktop dialog.
- **Stopping** — wait for the active model or operation to reach a terminal state.

The runtime does not silently fall back to a different model. If the selected model is
missing, use the first-run controls to download it or point XBrainLab to the expected
cache.

## Preserve useful diagnostic information

When reporting a problem, record:

- what you selected and the exact visible message;
- the workflow stage and dataset scope;
- whether the action completed, failed, was blocked, or was cancelled;
- the XBrainLab version or source revision;
- the relevant application log, after checking it for participant information.

Do not publish raw EEG data, participant identifiers, local paths, secrets, or an entire
diagnostics directory without review.

For product boundaries rather than a runtime problem, see
[Limits and safety](faq-limits.md).
