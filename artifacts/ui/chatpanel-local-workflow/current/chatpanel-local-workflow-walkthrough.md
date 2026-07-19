# ChatPanel Local Workflow Walkthrough

- status: `passed`
- failure reason: none
- runtime classification: `gpu-ready`
- model: `microsoft/Phi-4-mini-instruct`
- cache usage: `15.34 GB`
- first-run policy: `bypassed_without_persisting_settings`
- HF offline: `1`
- Transformers offline: `1`
- ready screenshot: `artifacts/ui/chatpanel-local-workflow/current/chatpanel-workflow-ready.png`
- elapsed seconds: `27.163`

## Turns

### Turn 1

- prompt: Check what is ready in the current XBrainLab workflow. Use the state query tool if needed, then answer in one short sentence.
- assistant: No data loaded. Next: Scan data source.
- new tool count: `1`
- screenshot: `artifacts/ui/chatpanel-local-workflow/current/chatpanel-workflow-turn-1.png`

### Turn 2

- prompt: Explain in one short sentence what EEG preprocessing prepares data for.
- assistant: EEG preprocessing prepares data for accurate analysis by removing noise and artifacts.
- new tool count: `0`
- screenshot: `artifacts/ui/chatpanel-local-workflow/current/chatpanel-workflow-turn-2.png`

## Executed Tools

- `query_state`: `ok` (1.131 ms)

## UI State

- send button: `Send`
- send button enabled: `True`
- input enabled: `True`
- chat processing: `False`
- controller processing: `False`

## Post-close Lifecycle

- passed: `True`
- runtime state: `closed`
- dispatcher state: `closed`
- controller released: `True`
- cleanup signal observed: `True`
- registered generation threads: `0`
- running generation threads: `0`
