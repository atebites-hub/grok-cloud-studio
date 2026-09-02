# Plugins

Primary (Python stdio MCP + Cursor plugin manifests):

- `plugins/a2a`
- `plugins/cursor-cloud`

Grok `--plugin-dir` is a grok **agent** flag (not headless). Opted-in seat mind
installs grok `plugin.json` plugins into seat `GROK_HOME` via
`install_mind_grok_plugins` / `grok plugin install --trust` (not Hermes
`plugin.yaml`; do not vendor hermes-agent; see `docs/studio/MIND.md` and
`tests/features/liv63_mind_plugins.feature`):

- `plugins/studio-mind` — `ticket`, `a2a_send`, `cloud_launch`
- `plugins/a2a` — `a2a_list_seats`, `a2a_send`
- `plugins/cursor-cloud` — Extra High `cloud_launch` / `cloud_list` / `cloud_status` / `cloud_result` (do not restack `cloud_followup` into `mind.py`)

```bash
grok plugin install ./plugins/a2a --trust
grok plugin install ./plugins/cursor-cloud --trust
```

Optional Node MCP servers (same tools, npm install in each dir):

- `plugins/gcs-a2a`
- `plugins/gcs-cursor-cloud`

Never commit tokens.
