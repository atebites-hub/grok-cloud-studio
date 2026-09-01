# studio-mind (seat GROK_HOME plugin)

Grok Agent SDK / MCP tools for opted-in seat mind: `ticket`, `a2a_send`,
`cloud_launch`. Grok `plugin.json`, not Hermes `plugin.yaml`.

`seat-mind-loop.sh` installs this directory (plus `plugins/a2a` and
`plugins/cursor-cloud`) into the seat `GROK_HOME` with
`install_mind_grok_plugins`:

```bash
GROK_HOME=$GCS_A2A_STATE/<seat>/grok-home \
  grok plugin install "$GCS_ROOT/plugins/studio-mind" --trust
```

That helper stamps `$GROK_HOME/gcs-root` so the copied `server.py` can
import repo scripts after initialize (handshake must not close; `python3 -u`).

`--plugin-dir` is a grok **agent** flag and cannot go on headless `grok`
(`--prompt-file` / `--resume`). `--trust` belongs on `plugin install`, not on
the mind argv. Already-installed / idempotent reinstall is success
(`MIND_PLUGIN_OK`), not `reason=install-fail`. If install is skipped (no grok,
missing dir, genuine fail), mind is MCP-only: seat `GROK_HOME/config.toml`
still owns taskboard stdio MCP (`taskboard --db`).

Not a Cursor `${workspaceFolder}` MCP. Not ACP `session/prompt`. Do not
vendor `NousResearch/hermes-agent`.

Python `PLUGINS` in `scripts/directors/mind.py` remain as `call_plugin` helpers
only — they are not a second agent loop.

Cursor CLI (`GCS_MIND_RUNNER=cursor`, or auto after `MIND_SWITCH`) does not get
this plugin or seat `GROK_HOME` taskboard MCP. Those do not transfer. Cursor
uses Cursor builtins (shell/files); `ticket`, `scripts/a2a/send.sh`, and
`scripts/launch-cloud-extra-high.sh` stay on PATH.
