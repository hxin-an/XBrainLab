# XBrainLab MCP Stdio Walkthrough

- client dependency boundary: Client script imports only Python standard-library modules; XBrainLab runtime dependencies stay in the spawned server process.
- server command: `/home/administrator/.cache/pypoetry/virtualenvs/xbrainlab-TKrzxeIe-py3.12/bin/python scripts/dev/run_mcp_server.py`
- initialized: `True`
- tool count: `28`
- has scan_source: `True`
- scan_source taxonomy: `data_interpretation`
- adapter mode: `headless_mcp_stdio`
- adapter transport: `stdio`
- session id stable: `True`
- UI refresh supported: `False`
- UI refresh boundary: This MCP server owns a headless ApplicationService session and does not refresh a desktop UI.
- train result boundary: `precondition`
- job boundary reached: `False`
- long-running job supported: `False`

## Tool Calls

### scan_source

- isError: `False`
- status: `ok`
- text: Scanned source and found 1 EEG file(s).

### preview_interpretation

- isError: `False`
- status: `ok`
- text: Interpretation preview ready.

### validate_interpretation

- isError: `False`
- status: `ok`
- text: Interpretation validation: needs_confirmation.

### train

- isError: `True`
- status: `failed`
- text: Load raw data before training.; Generate datasets before training.; Select a model before training.; Configure training options before training.
