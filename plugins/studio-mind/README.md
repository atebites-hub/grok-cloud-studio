# studio-mind (seat GROK_HOME plugin)

Grok Agent SDK / MCP tools for opted-in seat mind: `ticket`, `a2a_send`,
`cloud_launch`.

`seat-mind-loop.sh` installs this directory **and** `plugins/a2a` /
`plugins/cursor-cloud` into the seat `GROK_HOME` with grok `plugin.json`
(not Hermes `plugin.yaml`; do not vendor hermes-agent):

```bash
GROK_HOME=$GCS_A2A_STATE/<seat>/grok-home \
  grok plugin install "$GCS_ROOT/plugins/studio-mind" --trust
GROK_HOME=$GCS_A2A_STATE/<seat>/grok-home \
  grok plugin install "$GCS_ROOT/plugins/a2a" --trust
GROK_HOME=$GCS_A2A_STATE/<seat>/grok-home \
  grok plugin install "$GCS_ROOT/plugins/cursor-cloud" --trust
```

`--plugin-dir` is a grok **agent** flag and cannot go on headless `grok`
(`--prompt-file` / `--resume`). `--trust` belongs on `plugin install`, not on
the mind argv. Already-installed / idempotent reinstall is success
(`MIND_PLUGIN_OK`), not `reason=install-fail`. Install stamps
`$GROK_HOME/gcs-root` with `GCS_ROOT` so the copied `server.py` still imports
repo scripts. `mcp.json` runs `python3 -u server.py`. The MCP handshake must
not close on `initialize`: stay connected through `notifications/initialized`
then `tools/list` on the same stdio pid. If install is skipped (no grok,
missing dir, genuine fail), mind is MCP-only: seat `GROK_HOME/config.toml`
still owns taskboard stdio MCP (`taskboard --db`) and chrome-devtools
stdio MCP (`npx -y chrome-devtools-mcp@latest`). chrome-devtools is not a
`grok plugin install` target. That is the live Chrome for qa-a playtest
of `http://127.0.0.1:5173/` (`tools/call navigate_page` then
`take_screenshot` in one session). Not this studio-mind plugin. Not Cursor
`${workspaceFolder}`. Not ACP `session/prompt`. Two catalogs. Python
`mind.py` does not call chrome-devtools.

Python `PLUGINS` in `scripts/directors/mind.py` remain as `call_plugin` helpers
only — they are not a second agent loop.

Cursor CLI (`GCS_MIND_RUNNER=cursor`, or auto after `MIND_SWITCH`) does not get
this plugin, seat `GROK_HOME` taskboard MCP, or chrome-devtools. Those do not
transfer. Cursor uses Cursor builtins (shell/files); `ticket`,
`scripts/a2a/send.sh`, and `scripts/launch-cloud-extra-high.sh` stay on PATH.

