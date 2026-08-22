# Run an EEG workflow

Move through the desktop workflow in order. Each later stage depends on the data and
choices established earlier.

## Import and review the dataset

Import is a review step, not just a file picker. Confirm the selected recordings, label
source, label placement, class map, and subject/session/task/run metadata before you
apply the import.

Stop if an event code, annotation, label row, or unit cannot be explained from the
dataset documentation. XBrainLab can present a candidate interpretation; it cannot
recover missing experimental meaning.

## Preprocess the signal

Open **Preprocess** after the reviewed import is active. Available operations include
filtering, resampling, rereferencing, normalization, and channel selection.

Before applying an operation:

1. Check the current sampling rate, units, and channel types.
2. Enter values from the study protocol, not from a generic preset.
3. Compare the visible signal before and after the operation.
4. Confirm the operation history records the expected order.
5. Avoid fitting preprocessing choices on held-out evaluation data.

If an action is disabled, check its prerequisite in
[Troubleshooting](troubleshooting.md#an-action-is-disabled).

## Create epochs

Use **Create EEG Epochs** to convert reviewed events into trial windows. Select an event
that represents the trial anchor, then enter the time window and baseline required by
the protocol.

Check the epoch count for each class and review rejected boundary epochs. If a response,
artifact, or boundary marker was selected as the anchor, return to the event decision
before continuing.

## Configure the split

Open **Dataset Splitting** and choose the held-out unit that matches the research
question.

| Research question | Split to consider |
| --- | --- |
| New trials from known recordings | Trial, with explicit leakage checks |
| Another run or visit | Run or session |
| Unseen participants | Subject |
| Within-subject adaptation | An explicit within-subject design |

Confirm that each fold contains the intended classes and that fitted preprocessing
state does not cross the split boundary.

## Select a model and train

In **Training**:

1. Open **Dataset Splitting** and review the fold plan.
2. Open **Model Selection** and choose a model compatible with the input shape.
3. Open **Training Setting** and review epochs, batch size, optimizer-related values,
   and execution resources.
4. Select **Start Training** and respond to any required resource confirmation.
5. Wait for a completed, stopped, or failed terminal state before treating the run as
   part of history.

Training curves show optimizer behaviour. They do not establish generalization or
scientific validity.

## Review evaluation

Open **Evaluation** after a compatible training result exists. Select the fold, run, and
split before reading a confusion matrix, class values, metrics, or model details.

An **All Folds** summary is meaningful only when the underlying test masks and cohorts
are compatible. Preserve the fold-level results even when a summary is available.

## Compute and inspect saliency

Open **Visualization** and select the trained run, input, class, and method. Use
**Compute Saliency** when the required data and model are available, then wait for the
operation to finish.

Treat the result as model sensitivity for that identified input and method. Check the
channel order, montage, scaling, display normalization, and method stability before
interpreting a pattern.

## Change an earlier decision

If you need to change imported data, preprocessing, epoch definitions, or split
membership, start from the earliest affected stage. Resetting is safer than preserving
downstream results whose inputs no longer match.

Keep the dataset identity, import decisions, operation history, epoch settings, split,
model settings, seed, run identity, and terminal result together.
