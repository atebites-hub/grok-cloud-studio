# Taskboard

Studio mission control is **[tcarac/taskboard](https://github.com/tcarac/taskboard)** — ticket CLI plus HTTP `/mcp`.

Agent Kanban (`ak`, AMA, `scripts/studio/agent-kanban/`) was removed from this control plane. Do not reconnect it. Do not run `ak start` from the A2A bus.

## What Directors should use

- Ticket CLI from the taskboard checkout (create / move / comment).
- MCP over HTTP `/mcp` when the taskboard server is running locally.
- GROW keep-alives (`ACP_PING STATUS/CONTINUE`) allow a ticket move as work. They are not a LAUNCH assigner.

`start-seat-daemon.sh` / `seat-daemon-common.sh` install thin wrappers on the grok serve PATH (`$GROK_HOME/bin` and `~/.grok/bin`) so a Director can exec these against the studio SQLite file without a box-local symlink:

```bash
taskboard ticket move <ID> --status in_progress
taskboard ticket create --title "…" --priority medium
ticket list
ticket move <ID> --status done
tb move <ID> --status done
tb create --title "…"
```

Wrappers always pass `--db "$GCS_TASKBOARD_DB"` (default `$GCS_A2A_STATE/taskboard/taskboard.db`). Set `TASKBOARD_BIN` if the host binary is not already discoverable (`$GCS_ROOT/bin/taskboard` or `command -v`). Floor keep-alives still say `taskboard ticket move`.

On seat start, `install_seat_grok_mcp` (also `scripts/directors/install-grok-mcp.sh`) registers **stdio MCP** in that seat's isolated `$GROK_HOME/config.toml`:

```toml
[compat.cursor]
mcps = false

[mcp_servers.taskboard]
command = "/absolute/path/to/taskboard"
args = ["--db", "/absolute/path/to/taskboard.db", "mcp"]
```

That is the grok serve config. Isolated `GROK_HOME` does not inherit `~/.grok/config.toml`. Cursor `${workspaceFolder}` never expands under grok; `.cursor/mcp.json` is not the serve config. `./doctor.sh` WARNs if a seat `config.toml` still contains `${workspaceFolder}`. Refreshing MCP config does not remint a live serve.

This repository does not vendor the taskboard binary. Point seats at your local taskboard checkout the same way you point Extra High at `GCS_CLOUD_REPO`.

The HTML files under `scripts/studio/dashboard/` remain LEGACY and are not the board.
