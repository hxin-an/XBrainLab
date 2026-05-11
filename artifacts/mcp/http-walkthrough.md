# MCP HTTP Walkthrough

- transport: `http`
- endpoint: `127.0.0.1:<ephemeral>/mcp`
- session id: `mcp-http-06a1543fa565`
- tools listed: `28`
- scan ok: `True`
- preview ok: `True`
- train job: `mcp-http-job-0e72dcda1545`
- job listed: `True`
- job status before cancel: `running`
- job status after cancel: `cancelled`

## Boundaries

- The HTTP client uses Python standard-library HTTP and JSON only. XBrainLab EEG, PyQt, PyTorch, and local LLM dependencies remain in the server process.
- This is a headless ApplicationService MCP session. It does not control or refresh the desktop UI.
- HTTP train job status and cancel are available for the headless session. Evaluation/visualization jobs, persistence, and recovery are not enabled in this slice.
