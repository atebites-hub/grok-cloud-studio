# studio-mind (Grok `--plugin-dir`)

Grok Agent SDK inject for opted-in seat mind. `mind.py` passes

`--plugin-dir $GCS_ROOT/plugins/studio-mind`

when this directory exists. Tools: `ticket`, `a2a_send`, `cloud_launch`.

Not a Cursor `${workspaceFolder}` MCP. Not ACP `session/prompt`. Seat
`GROK_HOME/config.toml` still owns taskboard stdio MCP (`taskboard --db`).

If this directory is missing, Python `PLUGINS` in `scripts/directors/mind.py`
remain as `call_plugin` helpers only — grok will not see those tools unless
they are registered some other way.
