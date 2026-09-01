# Plugins

Two Cursor/Grok MCP plugins ship in-tree plus seat-mind `studio-mind`. All
speak JSON-RPC stdio (Content-Length; set `GCS_MCP_NDJSON=1` for newline JSON).
Shared A2A/cloud implementation: `scripts/mcp/gcs_mcp.py`.

Grok-bot-like remaining (Living Sky **LIV-63**, after #76 on main): each
plugin has grok `plugin.json` at the plugin root (not Hermes `plugin.yaml`).
`seat-mind-loop.sh` `install_mind_grok_plugins` runs `grok plugin install
--trust` of `plugins/studio-mind`, `plugins/a2a`, and `plugins/cursor-cloud`
into seat `GROK_HOME`. Copied servers honor `GCS_ROOT`. Do **not** vendor
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).
BDD: [`tests/features/liv63_mind_plugins.feature`](../tests/features/liv63_mind_plugins.feature).
Do not restack #47 `cloud_list` / `cloud_followup` into `mind.py` `PLUGINS`.

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
| `cloud_launch` | Extra High spawn. Returns after `CLOUD_LAUNCH_OK`; SDK waiter pings with context. Directors never block-wait. |
| `cloud_list` | `scripts/cloud/list_helper.py` — agent `status` plus latest-run `runStatus` (`RUNNING` vs `FINISHED`). ACTIVE+FINISHED leftovers are not workers |
| `cloud_status` | `scripts/cloud/status-cloud-agent.sh` |
| `cloud_result` | `scripts/cloud/result-cloud-agent.sh` (non-blocking context JSON; do not watch) |

```bash
grok plugin install ./plugins/cursor-cloud --trust
python3 plugins/cursor-cloud/server.py
```

Requires `GCS_CLOUD_REPO` / `CLOUD_REPO_URL` for create. `CURSOR_API_KEY` is read from the environment or `~/.config/cursor/agent.env` and is never returned in tool output.

## Cursor local plugins

Each plugin has grok `plugin.json` and Cursor `.cursor-plugin/plugin.json` with relative `mcpServers` (`./mcp.json`) and `./server.py`. No `..` path traversal in manifests.

Workspace umbrella (both planes):

```bash
grok plugin install . --trust
```

See root `.cursor-plugin/plugin.json` and `mcp.json`.

## Grok catalog browser (`chrome-devtools`)

Not in-tree. xAI Grok catalog live Chrome (Chrome DevTools MCP). Seat
`GROK_HOME/config.toml` registers stdio `npx -y chrome-devtools-mcp@latest`.
That is config.toml stdio, not `grok plugin install chrome-devtools`.
`seat-mind-loop.sh` does not install it.

qa-a uses this to visually playtest `http://127.0.0.1:5173/` via
`tools/call navigate_page` then `take_screenshot` in one session. Pytest
proves a grok-equivalent client can issue that call
(`scripts/directors/grok_catalog_mcp.py`). Not Cursor CLI.
Not Bot CloudAgent. Do not add chrome-devtools to `.cursor/mcp.json`.
Two catalogs. See `docs/studio/MIND.md`.
