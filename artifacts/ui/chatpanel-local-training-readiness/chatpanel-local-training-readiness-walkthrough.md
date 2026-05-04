# ChatPanel Local Training Readiness Walkthrough

- status: `passed`
- failure reason: none
- source path: `/tmp/xbrainlab_chatpanel_tool_chain/chatpanel_chain_raw.fif`
- dataset preparation ok: `True`
- runtime classification: `gpu-ready`
- model: `microsoft/Phi-4-mini-instruct`
- cache usage: `15.34 GB`
- HF offline: `1`
- Transformers offline: `1`
- ready screenshot: `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-ready.png`
- training confirmations observed: `1`
- evaluate blocked: `True`
- elapsed seconds: `37.948`

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
- screenshot: `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-1.png`

### Turn 2

- kind: `tool`
- prompt: Configure training for 1 epoch, batch size 2, learning rate 0.001, and device cpu. Reply with one short result sentence.
- expected tool: `configure_training`
- assistant: Training configured.
- new tools: `configure_training`
- screenshot: `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-2.png`

### Turn 3

- kind: `confirmation`
- prompt: Start training now with the current settings. If the app asks for confirmation, wait for that confirmation.
- expected tool: `start_training`
- assistant: Cancelled: Start training.
- new tools: ``
- screenshot: `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-3.png`

### Turn 4

- kind: `tool`
- prompt: Show visualization readiness for the active dataset. Use the visualization readiness tool and reply with one short result sentence.
- expected tool: `visualize`
- assistant: Visualization summary ready.
- new tools: `visualize`
- screenshot: `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-4.png`

### Turn 5

- kind: `tool`
- prompt: Show saliency readiness for the active dataset. Use the saliency readiness tool and reply with one short result sentence.
- expected tool: `saliency`
- assistant: Saliency parameters are not configured yet.
- new tools: `saliency`
- screenshot: `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-5.png`

### Turn 6

- kind: `blocked`
- prompt: Evaluate current training results. If evaluation is blocked, explain the blocked reason in one short user-facing sentence.
- expected tool: `evaluate`
- assistant: Assistant action is not available yet: Create a training plan before evaluating results.
- new tools: ``
- screenshot: `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-6.png`

## Executed Tools

- `set_model`: `ok` (55.312 ms)
- `configure_training`: `ok` (51.86 ms)
- `visualize`: `ok` (1.122 ms)
- `saliency`: `ok` (0.86 ms)

## Final State

- dataset available: `True`
- selected model: `EEGNet`
- has training option: `True`
- has trainer: `False`
- training running: `False`
- evaluation available: `False`
- evaluation plans: `0`

## UI State

- send button: `Send`
- send button enabled: `True`
- input enabled: `True`
- chat processing: `False`
- controller processing: `False`
