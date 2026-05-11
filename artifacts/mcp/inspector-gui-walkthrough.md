# MCP Inspector GUI Walkthrough

- status: `passed`
- claim boundary: Automated MCP Inspector GUI click-through against the Windows WSL client entry; not a human GUI session, full MCP client certification, or packaging release approval.
- client dependency boundary: The Inspector and Chrome run as external Windows client processes; the selected server entry launches the prepared XBrainLab WSL runtime wrapper.
- server: `xbrainlab-windows-wsl`
- inspector URL: `http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<redacted>`
- screenshot: `artifacts/mcp/inspector-gui-connected.png`

## Checks

- `inspector_url_seen`: `True`
- `connect_clicked`: `True`
- `connected_visible`: `True`
- `disconnect_visible`: `True`
- `server_name_visible`: `True`
- `tools_panel_visible`: `True`
- `command_prepopulated`: `True`
- `wrapper_argument_prepopulated`: `True`
- `screenshot_written`: `True`
- `tool_visible_scan_source`: `True`
- `tool_visible_preview_interpretation`: `True`
- `tool_visible_validate_interpretation`: `True`
- `tool_visible_apply_interpretation`: `True`

## Visible Tool Evidence

- `scan_source` / `Scan Source`: `True`
- `preview_interpretation` / `Preview Interpretation`: `True`
- `validate_interpretation` / `Validate Interpretation`: `True`
- `apply_interpretation` / `Apply Interpretation`: `True`

## Visible Text

```text
MCP Inspector v0.21.2
Transport Type
STDIO
Command
Arguments
Environment Variables
Server Entry
Servers File
Authentication
Configuration
Restart
Disconnect
Connected
xbrainlab
Version: 0.5.6
System
Resources
Prompts
Tools
Tasks
Apps
Ping
Sampling
Elicitations
Roots
Auth
Metadata
Tools
List ToolsClear
Scan Source
Scan a source path for EEG files, label carriers, and metadata.
Preview Interpretation
Build and preview a candidate data interpretation.
Validate Interpretation
Validate an interpretation candidate.
Apply Interpretation
Apply a validated interpretation to the active backend session.
Save Interpretation Recipe
Save the applied interpretation as a replayable recipe.
Reload Interpretation Recipe
Reload a recipe and re-run scan/preview/validation without applying.
Load Data
Load raw EEG files into the active study.
Attach Labels
Attach label files to already-loaded raw files.
Import Labels
Apply an explicit label import plan to loaded raw data.
Update Metadata
Update subject/session metadata for one or more loaded files.
Apply Smart Parse
Apply filename parser results to loaded-file metadata.
Remove Files
Remove loaded raw files by row/index.
Preprocess
Apply a preprocessing operation to the active study.
Create Epoch
Create epochs from preprocessed data.
Generate Dataset
Generate train/validation/test datasets from epoch data.
Clear Datasets
Clear generated datasets and any training plan tied to them.
Configure Training
Configure model and training hyperparameters.
Train
Start model training.
Stop Training
Stop an active training run.
Clear Training History
Clear training plan/run history while preserving current configuration.
Evaluate
Read evaluation metrics and run summaries from the active backend.
Visualize
Read visualization readiness and available view summaries.
Saliency
Configure or query saliency readiness.
Apply Montage
Apply confirmed channel montage positions to epoch data.
Query State
Read-only typed query through the application service.
Reset Preprocess
Reset preprocessing to loaded raw data and remove downstream artifacts.
Reset Session
Clear loaded data and downstream state.
New Session
Start a new single-backend session by clearing current state.
Select a tool
Select a tool from the list to view its details and run it
History
Clear
2. tools/list
▶
1. initialize
▶
Server Notifications
Clear

No notifications yet
```
