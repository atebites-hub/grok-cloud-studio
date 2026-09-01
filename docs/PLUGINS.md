# Plugins

Two Cursor/Grok MCP plugins ship in-tree. Both speak JSON-RPC stdio (Content-Length; set `GCS_MCP_NDJSON=1` for newline JSON). Shared implementation: `scripts/mcp/gcs_mcp.py`.

Grok-bot-like mind seats install these with `plugin.json` (not Hermes `plugin.yaml`) via `install_mind_grok_plugins` → `grok plugin install --trust`. Off-tree copies honor `GCS_ROOT` or the `GROK_HOME/gcs-root` stamp. Do **not** vendor `NousResearch/hermes-agent`. See `tests/features/liv63_mind_plugins.feature`.

## A2A (`plugins/a2a`)

| Tool | Action |
|---|---|
| `a2a_list_seats` | Seats from `docs/a2a/registry.json` |
| `a2a_send` | `scripts/a2a/send.sh [--from SEAT] <seat> <text>` |

```bash
grok plugin install ./plugins/a2a --trust
python3 -u plugins/a2a/server.py
```

## Cursor Cloud (`plugins/cursor-cloud`)

| Tool | Action |
|---|---|
| `cloud_launch` | `scripts/launch-cloud-extra-high.sh` |
| `cloud_status` | `scripts/cloud/status-cloud-agent.sh` |
| `cloud_result` | `scripts/cloud/result-cloud-agent.sh` |

```bash
grok plugin install ./plugins/cursor-cloud --trust
python3 -u plugins/cursor-cloud/server.py
```

Requires `GCS_CLOUD_REPO` / `CLOUD_REPO_URL` for create. `CURSOR_API_KEY` is read from the environment or `~/.config/cursor/agent.env` and is never returned in tool output. Do not restack hive-upgrade `cloud_list` / `cloud_followup` here (that is GCS #47).

## studio-mind (`plugins/studio-mind`)

Seat GROK_HOME MCP for `ticket`, `a2a_send`, and `cloud_launch`. Same grok `plugin.json` install path. Handshake must stay open after `initialize`.

## Cursor local plugins

Each plugin has `.cursor-plugin/plugin.json` with relative `mcpServers` (`./mcp.json`) and `./server.py`. No `..` path traversal in manifests.

Workspace umbrella (both planes):

```bash
grok plugin install . --trust
```

See root `.cursor-plugin/plugin.json` and `mcp.json`.
