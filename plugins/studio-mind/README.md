# studio-mind (seat GROK_HOME plugin)

Grok Agent SDK / MCP tools for opted-in seat mind: `ticket`, `a2a_send`,
`cloud_launch`.

`seat-mind-loop.sh` installs this directory into the seat `GROK_HOME` with:

```bash
GROK_HOME=$GCS_A2A_STATE/<seat>/grok-home \
  grok plugin install "$GCS_ROOT/plugins/studio-mind" --trust
```

`--plugin-dir` is a grok **agent** flag and cannot go on headless `grok`
(`--prompt-file` / `--resume`). `--trust` belongs on `plugin install`, not on
the mind argv. Already-installed / idempotent reinstall is success
(`MIND_PLUGIN_OK`), not `reason=install-fail`. If install is skipped (no grok,
missing dir, genuine fail), mind is MCP-only: seat `GROK_HOME/config.toml`
still owns taskboard stdio MCP (`taskboard --db`) and chrome-devtools
stdio MCP (`npx -y chrome-devtools-mcp@latest`). `seat-mind-loop.sh` also
installs the xAI marketplace plugin `chrome-devtools` into the same
`GROK_HOME` (`grok plugin install chrome-devtools --trust`). That is the
live Chrome for qa-a playtest of `http://127.0.0.1:5173/`. Not this
studio-mind plugin. Not Cursor `${workspaceFolder}`. Not ACP
`session/prompt`. Two catalogs.

Python `PLUGINS` in `scripts/directors/mind.py` remain as `call_plugin` helpers
only — they are not a second agent loop.

Cursor CLI (`GCS_MIND_RUNNER=cursor`, or auto after `MIND_SWITCH`) does not get
this plugin, seat `GROK_HOME` taskboard MCP, or chrome-devtools. Those do not
transfer. Cursor uses Cursor builtins (shell/files); `ticket`,
`scripts/a2a/send.sh`, and `scripts/launch-cloud-extra-high.sh` stay on PATH.

