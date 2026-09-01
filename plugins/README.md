# Plugins

Primary (Python stdio MCP + Cursor plugin manifests):

- `plugins/a2a`
- `plugins/cursor-cloud`

Grok `--plugin-dir` is a grok **agent** flag (not headless). Opted-in seat mind
installs this plugin into seat `GROK_HOME` via `grok plugin install --trust`
(see `docs/studio/MIND.md`):

- `plugins/studio-mind` — `ticket`, `a2a_send`, `cloud_launch`

Grok catalog live Chrome (not in-tree): marketplace `chrome-devtools`, also
registered as stdio `npx -y chrome-devtools-mcp@latest` in seat
`GROK_HOME/config.toml`. `seat-mind-loop.sh` runs
`grok plugin install chrome-devtools --trust`. qa-a playtests
`http://127.0.0.1:5173/`. Not Cursor CLI. Not Bot CloudAgent.

```bash
grok plugin install ./plugins/a2a --trust
grok plugin install ./plugins/cursor-cloud --trust
```

Optional Node MCP servers (same tools, npm install in each dir):

- `plugins/gcs-a2a`
- `plugins/gcs-cursor-cloud`

Never commit tokens.
