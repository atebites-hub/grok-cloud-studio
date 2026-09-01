# Plugins

Grok-bot-like mind plugins (Living Sky **LIV-63** remaining after #47/#76):
ticket, A2A, and cloud as grok `plugin.json` MCP — not Hermes `plugin.yaml`.
Do **not** vendor `NousResearch/hermes-agent`. Executable example:
[`tests/features/liv63_mind_plugins.feature`](../tests/features/liv63_mind_plugins.feature).

Two Cursor/Grok MCP plugins ship in-tree plus the mind ticket bundle. All speak
JSON-RPC stdio (Content-Length; set `GCS_MCP_NDJSON=1` for newline JSON). Shared
A2A/cloud implementation: `scripts/mcp/gcs_mcp.py`. Seat mind install:
`install_mind_grok_plugins` in `scripts/directors/seat-daemon-common.sh`.

## Ticket (`plugins/studio-mind`)

| Tool | Action |
|---|---|
| `ticket` | `TASKBOARD_BIN --db GCS_TASKBOARD_DB ticket <argv>` |
| `a2a_send` | `scripts/a2a/send.sh [--from SEAT] <seat> <text>` (also on the A2A plugin) |
| `cloud_launch` | `scripts/launch-cloud-extra-high.sh` (also on the cloud plugin) |

```bash
GROK_HOME=$GCS_A2A_STATE/<seat>/grok-home \
  grok plugin install ./plugins/studio-mind --trust
```

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

Each plugin has grok `plugin.json` (`mcpServers` → `./mcp.json`) and, for
Cursor, `.cursor-plugin/plugin.json` with relative `mcpServers` (`./mcp.json`)
and `./server.py`. No `..` path traversal in manifests. Not Hermes `plugin.yaml`.

Workspace umbrella (both planes):

```bash
grok plugin install . --trust
```

See root `.cursor-plugin/plugin.json` and `mcp.json`.
