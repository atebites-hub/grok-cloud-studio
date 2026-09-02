# Taskboard

Studio mission control is **[tcarac/taskboard](https://github.com/tcarac/taskboard)** — ticket CLI plus HTTP `/mcp`.

Source pin: git submodule `vendor/taskboard`, checked out at release tag **v0.6.0** (not floating `main`). Clone with `--recurse-submodules`, or after clone:

```bash
git submodule update --init --recursive
```

`./setup.sh` inits that submodule if missing. This repository does **not** vendor a compiled `taskboard` binary. If `vendor/taskboard` has no prebuilt, `scripts/studio/taskboard/install-taskboard.sh` uses brew tap or the matching v0.6.0 GitHub release tarball.

Agent Kanban (`ak`, AMA, `scripts/studio/agent-kanban/`) was removed from this control plane. Do not reconnect it. Do not run `ak start` from the A2A bus. `scripts/a2a/start-studio-bus.sh start`, `./recover.sh`, and `./doctor.sh` fail closed if `PALEMON_AK_BRIDGE` is on or the tree reappears.

## What Directors should use

- Ticket CLI from the taskboard checkout (create / move / comment).
- MCP over HTTP `/mcp` when the taskboard server is running locally.
- GROW keep-alives (`ACP_PING STATUS/CONTINUE`) allow a ticket move as work. They are not a LAUNCH assigner.

`start-seat-daemon.sh` / `seat-daemon-common.sh` install thin wrappers on the grok serve PATH (`$GROK_HOME/bin` and `~/.grok/bin`) so a Director can exec these against the studio SQLite file without a box-local symlink:

```bash
taskboard ticket move 01ARZ3NDEKTSV4RRFFQ69G5FAV --status in_progress
taskboard ticket create --title "…" --priority medium
ticket list
ticket move 01ARZ3NDEKTSV4RRFFQ69G5FAV --status done
tb move 01ARZ3NDEKTSV4RRFFQ69G5FAV --status done
tb create --title "…"
```

`ticket move` takes the **Crockford ULID** primary key (`oklog/ulid`, 26 chars). `ticket list` prints `[PREFIX-N] title - status (priority, ULID)` — move the ULID, not `T-1`, not `PAL-1`, not the display key. Seat wrappers fail closed if `move` is not a ULID.

Wrappers always pass `--db "$GCS_TASKBOARD_DB"` (default `$GCS_A2A_STATE/taskboard/taskboard.db`). Set `TASKBOARD_BIN` if the host binary is not already discoverable (`$GCS_ROOT/bin/taskboard` or `command -v`). Floor keep-alives still say `taskboard ticket move`.

On seat start, `install_seat_grok_mcp` (also `scripts/directors/install-grok-mcp.sh`) registers **stdio MCP** in that seat's isolated `$GROK_HOME/config.toml`:

```toml
[compat.cursor]
mcps = false

[mcp_servers.taskboard]
command = "/absolute/path/to/taskboard"
args = ["--db", "/absolute/path/to/taskboard.db", "mcp"]

[mcp_servers.linear]
url = "https://mcp.linear.app/mcp"
headers = { Authorization = "Bearer ${LINEAR_API_KEY}" }
```

That is the grok serve / grok mind config. Isolated `GROK_HOME` does not inherit `~/.grok/config.toml`. Cursor `${workspaceFolder}` never expands under grok; grok must not load `.cursor/mcp.json`. Seat start sets `[compat.cursor] mcps = false`. Living Sky Linear HTTP stays in this GROK_HOME catalog (`save_comment` on `LIV-*`). Do not copy GROK_HOME into Cursor CLI. `./doctor.sh` WARNs if a seat `config.toml` still contains `${workspaceFolder}`, or if an **existing** catalog is missing `[mcp_servers.taskboard]` / is not `taskboard --db <absolute db> mcp` (`scripts/directors/seat_grok_mcp.py lint`; tokens `missing-taskboard-table`, `args-not-db-mcp`, `db-not-absolute`). Doctor does not write factory catalogs and does not remint a live serve. Refreshing MCP config does not remint a live serve.

Cursor CLI uses a **second catalog**: checkout `.cursor/mcp.json` wrapping `scripts/studio/taskboard/run-mcp.sh` (`taskboard --db $DB mcp`) **and** Linear HTTP (`https://mcp.linear.app/mcp`, `Bearer ${LINEAR_API_KEY}`). Linear + taskboard only. Do not copy `GROK_HOME` MCP into Cursor CLI. Two catalogs. Never fake a transfer. Studio Linear is Living Sky (linear.app/livingsky, team Livingsky / LIV). NEVER Black Swan Money. No Agent Kanban. No secrets, private GitHub URLs, or MagicDNS hostnames in that file.

This repository does not vendor the taskboard binary. The IaC pin is `vendor/taskboard` (submodule, v0.6.0). Host install still uses brew or the v0.6.0 tarball when that checkout has no prebuilt. Point seats at the discovered binary (`TASKBOARD_BIN` / `$GCS_ROOT/bin/taskboard`) the same way you point Cursor Cloud at `GCS_CLOUD_REPO`.

Host process scripts (wipe box): `scripts/studio/taskboard/` —
`setup-taskboard.sh` (board-only start/stop/wipe + host `ticket`/`tb` PATH
links), `install-taskboard.sh`, `start-taskboard.sh` (UI `127.0.0.1:3010`),
`mcp-http.sh` (MCP `127.0.0.1:3011`), `run-mcp.sh` (Cursor CLI stdio).
`./setup.sh` calls `setup-taskboard.sh start`. `./cleanup.sh` calls
`setup-taskboard.sh stop` (or `wipe` when `CLEANUP_WIPE_STATE=1`).
`./recover.sh` still starts the leaf UI/MCP scripts when a port is down
(no brew/tarball as a recover side effect). Palemon floor recreate:
`docs/studio/WIPE.md`. Two-runtime mind law: `docs/studio/MIND.md`.
Studio Linear is Living Sky (linear.app/livingsky, team Livingsky / LIV).

## Maintainer kit (start / health / docs)

Studio-ops operates the **host** board with `scripts/studio/taskboard/maintainer.sh`:

```bash
bash scripts/studio/taskboard/maintainer.sh start    # UI + MCP HTTP
bash scripts/studio/taskboard/maintainer.sh health    # health-taskboard.sh
bash scripts/studio/taskboard/maintainer.sh docs
```

`health-taskboard.sh` is board-only. It is **not** `./health_check.sh` (studio DR: hub + ports + mind) and **not** `fleet-shepherd.py` (GCS #112 TASKBOARD_HEALTH probe). GET `/health` on `:3011` is not a usable board. Healthy means the SQLite file exists, the UI is up, and either `taskboard --db $DB ticket list` succeeds or `POST /mcp` returns 2xx. Seat stdio MCP stays isolated `GROK_HOME/config.toml` (GCS #100); this kit does not write that catalog.

`scripts/directors/fleet-shepherd.py` probes this board every cycle: the SQLite file (`GCS_TASKBOARD_DB` or `$GCS_A2A_STATE/taskboard/taskboard.db`) plus `ticket list` (`taskboard --db $DB ticket list`) **or** HTTP `POST /mcp` (default `http://127.0.0.1:3011/mcp`). It logs `TASKBOARD_HEALTH_OK` or `TASKBOARD_HEALTH_FAIL`. It does not start the UI, write seat `GROK_HOME` MCP, or reconnect `ak`.

Never reconnect Agent Kanban (`ak start`, `scripts/studio/agent-kanban`). Studio Linear is Living Sky (`linear.app/livingsky`, team Livingsky / `LIV`). NEVER Black Swan Money. Never print `CURSOR_API_KEY`. Never vendor Hermes. Never Bot CloudAgent.

The HTML files under `scripts/studio/dashboard/` remain LEGACY and are not the board. Do not rebuild a snowflake dashboard.

## studio-ops pin bump (LIV-86)

Source of truth is `scripts/studio/taskboard/PIN` (**v0.6.0** on main; matches `.gitmodules` `branch = v0.6.0`). Do not remint that pin unless you are applying a newer `vX.Y.Z` release. Do not float `main`.

```bash
bash scripts/studio/taskboard/upgrade-taskboard.sh --check
bash scripts/studio/taskboard/upgrade-taskboard.sh --dry-run v0.7.0
# apply writes PIN + .gitmodules branch, then:
bash scripts/studio/taskboard/upgrade-taskboard.sh --apply vX.Y.Z
bash scripts/studio/taskboard/install-taskboard.sh
```

`--apply` does **not** compile (`go build` / `make build`), does **not** vendor a binary blob, does **not** reconnect Agent Kanban, and does **not** copy `GROK_HOME` MCP into Cursor CLI. Seat stdio MCP stays `taskboard --db $GCS_TASKBOARD_DB mcp` in isolated `GROK_HOME/config.toml`. This is not the fleet-shepherd health probe.
