# MCP HTTP Walkthrough

- transport: `http`
- endpoint: `127.0.0.1:<ephemeral>/mcp`
- session id: `mcp-http-dec6e5b4e9b7`
- tools listed: `28`
- scan ok: `True`
- preview ok: `True`
- long-running boundary: `long_running_job_required`

## Boundaries

- The HTTP client uses Python standard-library HTTP and JSON only. XBrainLab EEG, PyQt, PyTorch, and local LLM dependencies remain in the server process.
- This is a headless ApplicationService MCP session. It does not control or refresh the desktop UI.
- HTTP transport baseline is available, but train/eval long-running job progress and cancel are not enabled in this slice.
