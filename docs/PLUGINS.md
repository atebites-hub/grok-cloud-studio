# Plugins

Two Cursor/Grok MCP plugins ship in-tree. Both speak JSON-RPC stdio (Content-Length; set `GCS_MCP_NDJSON=1` for newline JSON). Shared implementation: `scripts/mcp/gcs_mcp.py`.

## A2A (`plugins/a2a`)

| Tool | Action |
|---|---|
| `a2a_list_seats` | Seats from `docs/a2a/registry.json` |
| `a2a_send` | `scripts/a2a/send.sh [--from SEAT] <seat> <text>` |

```bash
grok plugin install ./plugins/a2a --trust
python3 plugins/a2a/server.py
```

## Cursor Cloud (`plugins/cursor-cloud`)

| Tool | Action |
|---|---|
| `cloud_launch` | `scripts/launch-cloud-extra-high.sh` |
| `cloud_status` | `scripts/cloud/status-cloud-agent.sh` |
| `cloud_result` | `scripts/cloud/result-cloud-agent.sh` |

```bash
grok plugin install ./plugins/cursor-cloud --trust
python3 plugins/cursor-cloud/server.py
```

Requires `GCS_CLOUD_REPO` / `CLOUD_REPO_URL` for create. `CURSOR_API_KEY` is read from the environment or `~/.config/cursor/agent.env` and is never returned in tool output.

## Cursor local plugins

Each plugin has `.cursor-plugin/plugin.json` with relative `mcpServers` (`./mcp.json`) and `./server.py`. No `..` path traversal in manifests.

Workspace umbrella (both planes):

```bash
grok plugin install . --trust
```

See root `.cursor-plugin/plugin.json` and `mcp.json`.

## Grok catalog browser (`chrome-devtools`)

Not in-tree. xAI marketplace plugin `chrome-devtools` (Chrome DevTools MCP:
live Chrome). Seat `GROK_HOME/config.toml` also registers stdio
`npx -y chrome-devtools-mcp@latest`. `seat-mind-loop.sh` runs
`grok plugin install chrome-devtools --trust` with that seat `GROK_HOME`.

```bash
GROK_HOME=$GCS_A2A_STATE/<seat>/grok-home \
  grok plugin install chrome-devtools --trust
```

qa-a uses this to visually playtest `http://127.0.0.1:5173/`. Not Cursor CLI.
Not Bot CloudAgent. Do not add chrome-devtools to `.cursor/mcp.json`. Two
catalogs. See `docs/studio/MIND.md`.
