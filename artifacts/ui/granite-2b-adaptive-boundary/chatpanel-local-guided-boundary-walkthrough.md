# ChatPanel Local Adaptive Workflow Boundary Walkthrough

- status: `passed`
- generated at (UTC): `2026-07-28T17:13:37.998537+00:00`
- failure reason: none
- source path: `/tmp/xbrainlab_chatpanel_tool_chain/chatpanel_chain_raw.fif`
- source commit: `56d79e38e75029707418c928c55256aea3b526a4`
- source digest: `39a02ed0ad30ca8991e3a9f8c89fe50d25bfe4efad8e2b7919079178a8011f50`
- dirty source: `True`
- requested model: `ibm-granite/granite-3.3-2b-instruct`
- loaded model: `ibm-granite/granite-3.3-2b-instruct`
- runtime classification: `gpu-ready`
- runtime phase: `ready`
- fallback used: `False`
- turn scope source: `request_text`
- resolved turn scope: `guided_workflow`
- terminal command: `None`
- legacy mode selector present: `False`
- expected auto-chain: `scan_source, preview_interpretation, validate_interpretation`
- boundary generation: `4`
- workflow handoff request: `445123ac08d5493ca7f936e79f8d5962`
- workflow decision fields: `metadata_review, label_matching`
- wizard target step: `Review Metadata`
- post-cancel generation: `4`
- shutdown: `completed`
- elapsed seconds: `35.64`

## Screenshots

- ready: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/granite-2b-adaptive-boundary/chatpanel-guided-boundary-ready.png` (`796x796`, sha256 `b6f11fbc3445dc143fe7f674425ee07367749758a5b35435d8906d88f9ce8693`)
- auto chain complete: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/granite-2b-adaptive-boundary/chatpanel-guided-auto-chain-complete.png` (`796x796`, sha256 `2031e338ddc0c2a666bf20364798b72f9354a80c5cb83307d0258cb3c4b2ab2a`)
- workflow dialog open: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/granite-2b-adaptive-boundary/chatpanel-guided-workflow-dialog-open.png` (`752x752`, sha256 `fa0c6fc63c152ab354768e5c630a13bb13d0c4bdef53d1c31ea413a8fc64c6a5`)
- post cancel: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/granite-2b-adaptive-boundary/chatpanel-guided-post-cancel.png` (`796x796`, sha256 `6f31676abe8de0c8c80a15fddb6f74a17ec9a1af10a55d98c25fe9c0731f1d63`)
- failure: `` (`unavailable`, sha256 ``)

## Command Publications

- `scan_source`: generation `2`, usable `True`
- `preview_interpretation`: generation `3`, usable `True`
- `validate_interpretation`: generation `4`, usable `True`

## Workflow UI Handoff Boundary

- typed handoff observed: `True`
- dialog opened: `True`
- dialog class: `XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.DataInterpretationPreviewDialog`
- dialog title: `Import EEG Data`
- target step: `Review Metadata`
- cancel clicked: `True`
- state unchanged: `True`
- apply completion observed: `False`

## Claim Boundary

This is deterministic offscreen/local-runtime product evidence. Offscreen evidence is not human Windows desktop acceptance.
