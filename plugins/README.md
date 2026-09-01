# Plugins

Primary (Python stdio MCP + Cursor plugin manifests):

- `plugins/a2a`
- `plugins/cursor-cloud`

Grok `--plugin-dir` is a grok **agent** flag (not headless). Opted-in seat mind
installs grok-bot-like plugins into seat `GROK_HOME` via `grok plugin install --trust`
(`plugin.json`, not Hermes `plugin.yaml`; `GROK_HOME/gcs-root` stamp). Do not
vendor `hermes-agent` (see `docs/studio/MIND.md`):

- `plugins/studio-mind` — `ticket`, `a2a_send`, `cloud_launch`
- `plugins/a2a` — `a2a_list_seats`, `a2a_send`
- `plugins/cursor-cloud` — `cloud_launch`, `cloud_status`, `cloud_result`

```bash
grok plugin install ./plugins/a2a --trust
grok plugin install ./plugins/cursor-cloud --trust
grok plugin install ./plugins/studio-mind --trust
```

Optional Node MCP servers (same tools, npm install in each dir):

- `plugins/gcs-a2a`
- `plugins/gcs-cursor-cloud`

Never commit tokens.
