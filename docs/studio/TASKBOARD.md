# Taskboard

Studio mission control is **[tcarac/taskboard](https://github.com/tcarac/taskboard)** — ticket CLI plus HTTP `/mcp`.

Source pin: git submodule `vendor/taskboard`, checked out at release tag **v0.6.0** (not floating `main`). Clone with `--recurse-submodules`, or after clone:

```bash
git submodule update --init --recursive
```

`./setup.sh` inits that submodule if missing. This repository does **not** vendor a compiled `taskboard` binary. If `vendor/taskboard` has no prebuilt, `scripts/studio/taskboard/install-taskboard.sh` uses brew tap or the matching v0.6.0 GitHub release tarball.

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

That is the grok serve config. Isolated `GROK_HOME` does not inherit `~/.grok/config.toml`. Cursor `${workspaceFolder}` never expands under grok; grok must not load `.cursor/mcp.json`. Seat start sets `[compat.cursor] mcps = false`. `./doctor.sh` WARNs if a seat `config.toml` still contains `${workspaceFolder}`, or if an **existing** catalog is missing `[mcp_servers.taskboard]` / is not `taskboard --db <absolute db> mcp` (`scripts/directors/seat_grok_mcp.py lint`; tokens `missing-taskboard-table`, `args-not-db-mcp`). Doctor does not write factory catalogs and does not remint a live serve. Refreshing MCP config does not remint a live serve.

Cursor CLI uses a **second catalog**: checkout `.cursor/mcp.json` wrapping `scripts/studio/taskboard/run-mcp.sh` (`taskboard --db $DB mcp`) **and** Linear HTTP (`https://mcp.linear.app/mcp`, `Bearer ${LINEAR_API_KEY}`). Linear + taskboard only. Do not copy `GROK_HOME` MCP into Cursor CLI. Two catalogs. Never fake a transfer. Studio Linear is Living Sky (linear.app/livingsky, team Livingsky / LIV). NEVER Black Swan Money. No Agent Kanban. No secrets, private GitHub URLs, or MagicDNS hostnames in that file.

This repository does not vendor the taskboard binary. The IaC pin is `vendor/taskboard` (submodule, v0.6.0). Host install still uses brew or the v0.6.0 tarball when that checkout has no prebuilt. Point seats at the discovered binary (`TASKBOARD_BIN` / `$GCS_ROOT/bin/taskboard`) the same way you point Cursor Cloud at `GCS_CLOUD_REPO`.

Host process scripts (wipe box): `scripts/studio/taskboard/` — `install-taskboard.sh`, `start-taskboard.sh` (UI `127.0.0.1:3010`), `mcp-http.sh` (MCP `127.0.0.1:3011`), `run-mcp.sh` (Cursor CLI stdio). Palemon floor recreate: `docs/studio/WIPE.md`. Two-runtime mind law: `docs/studio/MIND.md`.

## Maintainer kit (start / health / docs)

Studio-ops operates the **host** board with `scripts/studio/taskboard/maintainer.sh`:

```bash
bash scripts/studio/taskboard/maintainer.sh start    # UI + MCP HTTP
bash scripts/studio/taskboard/maintainer.sh health    # health-taskboard.sh
bash scripts/studio/taskboard/maintainer.sh docs
```

`health-taskboard.sh` is board-only. It is **not** `./health_check.sh` (studio DR: hub + ports + mind) and **not** `fleet-shepherd.py` (GCS #112 orphan Extra High probe). GET `/health` on `:3011` is not a usable board. Healthy means the SQLite file exists, the UI is up, and either `taskboard --db $DB ticket list` succeeds or `POST /mcp` returns 2xx. Seat stdio MCP stays isolated `GROK_HOME/config.toml` (GCS #100); this kit does not write that catalog.

Never reconnect Agent Kanban (`ak start`, `scripts/studio/agent-kanban`). Studio Linear is Living Sky (`linear.app/livingsky`, team Livingsky / `LIV`). NEVER Black Swan Money. Never print `CURSOR_API_KEY`. Never vendor Hermes. Never Bot CloudAgent.

The HTML files under `scripts/studio/dashboard/` remain LEGACY and are not the board.
