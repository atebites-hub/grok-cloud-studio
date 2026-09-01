# Studio taskboard (host)

tcarac/taskboard v0.6.0 is the studio board: Kanban UI plus stdio MCP. This
directory is the **wipe-box host process** layer. Seats still talk to the
SQLite file through wrappers (`docs/studio/TASKBOARD.md`). Agent Kanban
(`ak`, AMA, `scripts/studio/agent-kanban/`) stays gone.

## Maintainer kit (start / health / docs)

Studio-ops entrypoint (distinct from fleet-shepherd GCS #112 and seat
stdio MCP GCS #100). GET `/health` is not a usable board. Living Sky
(`LIV`) only; NEVER Black Swan Money.

```bash
bash scripts/studio/taskboard/maintainer.sh start    # start-taskboard.sh + mcp-http.sh
bash scripts/studio/taskboard/health-taskboard.sh    # DB + UI + ticket list OR POST /mcp
bash scripts/studio/taskboard/maintainer.sh docs
```

Pin file: `PIN` (single source of truth). studio-ops upgrades with
`upgrade-taskboard.sh` then `install-taskboard.sh`. Do not compile. Do not
rebuild a snowflake dashboard. Ticket move uses a Crockford ULID.

Do not vendor the `taskboard` binary into git. Source pin:
`vendor/taskboard` (submodule, **v0.6.0**). Clone with
`--recurse-submodules`, or `git submodule update --init --recursive`.
`./setup.sh` inits the submodule if missing. brew/tarball remains the
fallback when that checkout has no prebuilt.

Cursor CLI sees the board through checkout `.cursor/mcp.json` →
`run-mcp.sh` (`taskboard --db $DB mcp`) plus Linear HTTP. Linear +
taskboard only. That is the Cursor catalog.
Grok seats keep `GROK_HOME/config.toml` (taskboard stdio + Linear HTTP
catalog). Do not copy GROK_HOME MCP.
Two catalogs. Never fake a transfer. Studio Linear is Living Sky;
never Black Swan Money.

## After a machine wipe

From a grok-cloud-studio checkout (see `docs/studio/WIPE.md`):

```bash
# 1. Submodule (source pin v0.6.0) then binary (brew tap, else GitHub
#    release tarball — do not compile, do not vendor a blob)
git submodule update --init --recursive
bash scripts/studio/taskboard/setup-taskboard.sh start
bash scripts/studio/taskboard/setup-taskboard.sh status
# Host PATH: ticket / tb  (always --db $GCS_TASKBOARD_DB)

# Leaf equivalents if you need to start one process:
# bash scripts/studio/taskboard/install-taskboard.sh
# bash scripts/studio/taskboard/start-taskboard.sh start
# bash scripts/studio/taskboard/mcp-http.sh start

# 2. Then the bus (NO --daemons) with GCS_MIND_SEATS from studio.env
scripts/a2a/start-studio-bus.sh start

# 3. Optional Tailscale Serve — also started by ./setup.sh after the bus
#    PALEMON_TAILSCALE_SERVE=0 skips. Funnel stays off.
#    Host default: palemon-studio.panther-arctic.ts.net
bash scripts/studio/taskboard/start-tailscale-serve.sh start
```

Stop / board-only wipe (inboxes stay; Living Sky Linear is LIV, never Black Swan):

```bash
bash scripts/studio/taskboard/start-tailscale-serve.sh stop
bash scripts/studio/taskboard/setup-taskboard.sh stop
GCS_TASKBOARD_WIPE=1 bash scripts/studio/taskboard/setup-taskboard.sh wipe
# Leaf:
# bash scripts/studio/taskboard/mcp-http.sh stop
# bash scripts/studio/taskboard/start-taskboard.sh stop
```

## Ports

| What | Bind |
|---|---|
| UI | `http://127.0.0.1:3010` |
| MCP HTTP | `http://127.0.0.1:3011/mcp` |
| SQLite | `$GCS_A2A_STATE/taskboard/taskboard.db` |

`taskboard start` (v0.6.0) has `--port` and `--foreground`. It has no `--host`
flag and listens on `:3010`; access it as `127.0.0.1:3010`. Tailscale Serve
proxies `http://127.0.0.1:3010` and `:3011`.

## Env

| Knob | Role |
|---|---|
| `GCS_A2A_STATE` / `PALEMON_A2A_STATE` | Live state dir (studio.env + board DB) |
| `GCS_TASKBOARD_DB` | Override SQLite path |
| `TASKBOARD_BIN` | Override binary |
| `GCS_TASKBOARD_WIPE=1` | Allow `setup-taskboard.sh wipe` (`clear -f` + rm db) |
| `GCS_TASKBOARD_SKIP_READY=1` | Skip UI/MCP listen wait after start |
| `PALEMON_TAILSCALE_SERVE=0` | Skip Tailscale Serve |

Never print or commit `CURSOR_API_KEY` or Tailscale auth keys.

## Upgrade (studio-ops)

```bash
bash scripts/studio/taskboard/upgrade-taskboard.sh --check
bash scripts/studio/taskboard/upgrade-taskboard.sh --dry-run vX.Y.Z
bash scripts/studio/taskboard/upgrade-taskboard.sh --apply vX.Y.Z
bash scripts/studio/taskboard/install-taskboard.sh
```

`--apply` writes `PIN` and `.gitmodules` `branch` for `vendor/taskboard`.
It does not float `main`, compile from source, vendor a blob, reconnect
`ak`, promote the LEGACY dashboard, or copy `GROK_HOME` into Cursor CLI.
