# Plugins & MCP

Grok Cloud Studio ships two optional stdio MCP plugins:

| Package | Tools |
|---|---|
| `plugins/gcs-a2a` | `a2a_list_seats`, `a2a_send` |
| `plugins/gcs-cursor-cloud` | `cloud_launch`, `cloud_status`, `cloud_result`, `cloud_followup` |

These wrap the bash entrypoints. Configure secrets via environment / `~/.config/cursor/agent.env` — never in repo files.

Grok Build MCP (`grok mcp`) is separate from Cursor IDE Connected plugins.
