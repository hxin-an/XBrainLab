# Use the Assistant

The optional Assistant can answer questions and request supported XBrainLab actions. It
uses a fixed local Granite model and does not send the workflow to a cloud model.

The Assistant is a second way to reach the same desktop workflow. It does not replace
the Dataset, Preprocess, Training, Evaluation, or Visualization controls.

## Enable the local runtime

Install the optional dependency group before launching XBrainLab:

```bash
poetry install --with llm
poetry run python run.py
```

Open **AI Assistant**. On first use, review the model size, cache location, and available
GPU/CPU resources before enabling or downloading the model. XBrainLab does not silently
switch to another model when the selected runtime is unavailable.

## What one message can do

For each message, the Assistant chooses one of two outcomes:

- reply with information or ask for a missing value; or
- propose one action that is available in the current workflow stage.

It does not run a multi-step pipeline from one message. After an action completes,
fails, is blocked, or is cancelled, send another message for the next action.

Examples:

- `What sampling rate is active?`
- `Resample the data to 250 Hz.`
- `Open channel selection.`
- `Start training.`

When a value is required, include it explicitly. The Assistant should ask rather than
inventing a path, frequency, label, file name, or setting.

## Confirmation and desktop dialogs

Some actions require confirmation. Review the action and parameters before approving
it. If the workflow changed after the request was created, XBrainLab blocks the stale
confirmation instead of applying it to new state.

Import, channel selection, montage, epoch, split, model, and training configuration use
the existing desktop dialogs. The Assistant can open the correct surface, but you make
the high-impact choices there. Opening a dialog is not completion; the Assistant waits
for the dialog or operation to finish.

The same rule applies to saliency: opening Visualization or starting the request is not
the final result. Wait for the matching computation to report completion or failure.

## Stop a request

Use the stop control in the Assistant when a response or operation should not continue.
Cancellation may take a moment while the model, dialog, or background operation reaches
a safe terminal state. Do not send a second action while the first one is still
stopping.

## Know the boundary

The local model can select the wrong action or misunderstand a long conversation.
Backend capability checks, parameter checks, confirmation, and GUI handoffs reduce the
risk, but they do not make the Assistant an autonomous research decision maker.

Review labels, preprocessing choices, splits, training settings, metrics, and saliency
with the same care you would use without the Assistant.

If the runtime does not become ready or a message remains busy, see
[Assistant troubleshooting](troubleshooting.md#assistant-is-unavailable-or-stays-busy).
