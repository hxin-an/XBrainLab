# XBrainLab MCP Inspector CLI Tools List

- command: `npx @modelcontextprotocol/inspector --cli --config artifacts/mcp/xbrainlab-mcp.json --server xbrainlab-windows-wsl --method tools/list`
- transport: `stdio`
- launch path: Windows-side Inspector CLI -> `wsl.exe` -> prepared XBrainLab runtime wrapper -> `ApplicationService` MCP server
- artifact: `inspector-cli-tools-list.json`
- tool count: `28`
- first tools: `scan_source`, `preview_interpretation`, `validate_interpretation`, `apply_interpretation`, `save_interpretation_recipe`, `reload_interpretation_recipe`
- `scan_source` listed: `True`
- `apply_interpretation` listed: `True`

This proves the committed MCP client config can be consumed by the official Inspector CLI in this workspace. It is not a GUI click-through.
