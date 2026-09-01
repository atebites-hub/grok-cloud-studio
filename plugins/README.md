# Plugins

Primary (Python stdio MCP + Cursor plugin manifests):

- `plugins/a2a`
- `plugins/cursor-cloud`

Grok `--plugin-dir` is a grok **agent** flag (not headless). Opted-in seat mind
installs this plugin into seat `GROK_HOME` via `grok plugin install --trust`
(see `docs/studio/MIND.md`):

- `plugins/studio-mind` — `ticket`, `a2a_send`, `cloud_launch`, `liv_stamp`

```bash
grok plugin install ./plugins/a2a --trust
grok plugin install ./plugins/cursor-cloud --trust
```

Optional Node MCP servers (same tools, npm install in each dir):

- `plugins/gcs-a2a`
- `plugins/gcs-cursor-cloud`

Never commit tokens.
