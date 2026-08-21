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
the mind argv. If install is skipped, mind is MCP-only: seat
`GROK_HOME/config.toml` still owns taskboard stdio MCP (`taskboard --db`).

Not a Cursor `${workspaceFolder}` MCP. Not ACP `session/prompt`.

Python `PLUGINS` in `scripts/directors/mind.py` remain as `call_plugin` helpers
only — they are not a second agent loop.
