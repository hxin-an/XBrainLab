# ChatPanel Local Training Completion Walkthrough

- status: `passed`
- failure reason: none
- source path: `/tmp/xbrainlab_chatpanel_training_completion/training_completion_raw.fif`
- training output dir: `/tmp/xbrainlab-chatpanel-training-completion-output`
- dataset preparation ok: `True`
- runtime classification: `gpu-ready`
- model: `microsoft/Phi-4-mini-instruct`
- cache usage: `15.34 GB`
- HF offline: `1`
- Transformers offline: `1`
- ready screenshot: `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-ready.png`
- trained screenshot: `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-3.png`
- training confirmations observed: `1`
- confirmation approved: `True`
- finished runs: `1`
- evaluation metrics available: `True`
- saliency configured: `True`
- saliency available: `True`
- elapsed seconds: `48.789`

## Dataset Preparation

- `scan_source`: `True`
- `preview_interpretation`: `True`
- `validate_interpretation`: `True`
- `apply_interpretation`: `True`
- `preprocess`: `True`
- `create_epoch`: `True`
- `generate_dataset`: `True`

## Turns

### Turn 1

- kind: `tool`
- prompt: Use EEGNet for the active dataset. Reply with one short result sentence.
- expected tool: `set_model`
- assistant: Model configured: EEGNet.
- new tools: `set_model`
- screenshot: `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-1.png`

### Turn 2

- kind: `tool`
- prompt: Configure training for 1 epoch, batch size 2, learning rate 0.001, device cpu, and output_dir /tmp/xbrainlab-chatpanel-training-completion-output. Reply with one short result sentence.
- expected tool: `configure_training`
- assistant: Training configured.
- new tools: `configure_training`
- screenshot: `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-2.png`

### Turn 3

- kind: `confirmation`
- prompt: Start training now with the current settings. If the app asks for confirmation, wait for that confirmation.
- expected tool: `start_training`
- assistant: Confirmed: Start training. Training started.
- new tools: `start_training`
- screenshot: `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-3.png`

### Turn 4

- kind: `tool`
- prompt: Evaluate the completed training results and summarize the metrics in one short user-facing sentence.
- expected tool: `evaluate`
- assistant: Evaluation summary ready.
- new tools: `evaluate`
- screenshot: `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-4.png`

### Turn 5

- kind: `tool`
- prompt: Configure saliency with method Gradient and params nt_samples 2, nt_samples_batch_size 1, stdevs 1.0. Reply with one short result sentence.
- expected tool: `saliency`
- assistant: Saliency parameters configured.
- new tools: `saliency`
- screenshot: `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-5.png`

### Turn 6

- kind: `tool`
- prompt: Use visualize for a post-training visualization summary. Reply with one short result sentence.
- expected tool: `visualize`
- assistant: Visualization summary ready.
- new tools: `visualize`
- screenshot: `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-6.png`

### Turn 7

- kind: `tool`
- prompt: Query saliency readiness for the trained model. Reply with one short result sentence.
- expected tool: `saliency`
- assistant: Saliency summary ready.
- new tools: `saliency`
- screenshot: `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-7.png`

## Executed Tools

- `set_model`: `ok` (43.509 ms)
- `configure_training`: `ok` (55.575 ms)
- `start_training`: `ok` (137.914 ms)
- `evaluate`: `ok` (3.391 ms)
- `saliency`: `ok` (13.431 ms)
- `visualize`: `ok` (0.946 ms)
- `saliency`: `ok` (0.868 ms)

## Final State

- dataset available: `True`
- selected model: `EEGNet`
- has training option: `True`
- output dir: `/tmp/xbrainlab-chatpanel-training-completion-output`
- has trainer: `True`
- training running: `False`
- finished runs: `1`
- evaluation available: `True`
- evaluation metrics available: `True`
- saliency configured: `True`
- saliency available: `True`

## UI State

- send button: `Send`
- send button enabled: `True`
- input enabled: `True`
- chat processing: `False`
- controller processing: `False`
