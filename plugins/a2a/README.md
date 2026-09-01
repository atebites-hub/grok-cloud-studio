# Grok Cloud Studio — A2A plugin

MCP tools for the local A2A hub:

- `a2a_list_seats` — seats from `docs/a2a/registry.json`
- `a2a_send` — POST a text ping via `scripts/a2a/send.sh`

## Install

From the Grok Cloud Studio repo root:

```bash
# Cursor local plugin (this folder)
# or Grok CLI:
grok plugin install ./plugins/a2a --trust
```

Stdio server: `python3 -u plugins/a2a/server.py` (Content-Length JSON-RPC;
`GCS_ROOT` or `GROK_HOME/gcs-root` after grok copies this dir). Grok
`plugin.json`, not Hermes `plugin.yaml`.

Requires the studio bus: `scripts/a2a/start-studio-bus.sh start`.
