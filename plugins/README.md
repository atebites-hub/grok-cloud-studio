# Plugins

Grok-bot-like mind plugins (ticket / A2A / cloud). Grok `plugin.json`, not
Hermes `plugin.yaml`. Do not vendor `NousResearch/hermes-agent`. Off-tree
copies handshake from `GROK_HOME/gcs-root`.

Primary (Python stdio MCP + grok `plugin.json` + Cursor plugin manifests):

- `plugins/studio-mind`
- `plugins/a2a`
- `plugins/cursor-cloud`

Grok `--plugin-dir` is a grok **agent** flag (not headless). Opted-in seat mind
installs these into seat `GROK_HOME` via `grok plugin install --trust`
(`install_mind_grok_plugins`, see `docs/studio/MIND.md`):

- `plugins/studio-mind` — `ticket` (plus `a2a_send`, `cloud_launch` helpers)
- `plugins/a2a` — `a2a_list_seats`, `a2a_send`
- `plugins/cursor-cloud` — `cloud_launch`, `cloud_list`, `cloud_status`, `cloud_result` (Extra High plane; do not restack `cloud_list` into `mind.py`)

```bash
grok plugin install ./plugins/studio-mind --trust
grok plugin install ./plugins/a2a --trust
grok plugin install ./plugins/cursor-cloud --trust
```

Optional Node MCP servers (same tools, npm install in each dir):

- `plugins/gcs-a2a`
- `plugins/gcs-cursor-cloud`

Never commit tokens.
