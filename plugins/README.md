# Plugins

Primary (Python stdio MCP + Cursor plugin manifests):

- `plugins/a2a`
- `plugins/cursor-cloud`

Grok `--plugin-dir` inject for opted-in seat mind (not Cursor `${workspaceFolder}`):

- `plugins/studio-mind` — `ticket`, `a2a_send`, `cloud_launch` (see `docs/studio/MIND.md`)

```bash
grok plugin install ./plugins/a2a --trust
grok plugin install ./plugins/cursor-cloud --trust
```

Optional Node MCP servers (same tools, npm install in each dir):

- `plugins/gcs-a2a`
- `plugins/gcs-cursor-cloud`

Never commit tokens.
