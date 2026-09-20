# How to wire the IDE's MCP endpoint for Claude Code

JetBrains IDEs (PhpStorm, PyCharm, GoLand — 2025.2 and later) ship a
built-in MCP server exposing code search, inspections and refactorings.
Its port is per-IDE-instance, so the endpoint is machine-local:
`.mcp.json` (Claude Code) and `.codex/config.toml` (Codex) are
gitignored.

## Steps

1. In the IDE: Settings → Tools → MCP Server → enable; note the port.
2. Create `.mcp.json` at the repository root (start from
   `.mcp.json.example`), substituting the port:

   ```json
   {
     "mcpServers": {
       "ide": { "url": "http://127.0.0.1:<port>/stream", "type": "http" }
     }
   }
   ```

3. Restart Claude Code in the repository; the `ide` server and its
   `mcp__ide__*` tools appear in the MCP list.

If the IDE restarts on a different port, update the `url` — nothing
else changes. Use only MCP servers you trust: tool output is data, not
instructions.
