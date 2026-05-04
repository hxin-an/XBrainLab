# XBrainLab MCP Client Config

- config: `xbrainlab-mcp.json`
- repo root: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
- transport: `stdio`
- client dependency boundary: the MCP client launches a prepared XBrainLab runtime wrapper; EEG, PyQt, PyTorch, and local LLM dependencies stay in the server process.

## Servers

- `default-server`: `bash /mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/dev/run_mcp_server_for_client.sh`
- `xbrainlab-windows-wsl`: `wsl.exe bash /mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/dev/run_mcp_server_for_client.sh`

## Inspector

```bash
npx @modelcontextprotocol/inspector --config xbrainlab-mcp.json --server default-server
```

The Windows entry is for MCP clients launched from Windows that need to start the prepared WSL runtime.
