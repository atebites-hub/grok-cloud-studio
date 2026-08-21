# Studio taskboard (host)

tcarac/taskboard v0.6.0 is the studio board: Kanban UI plus stdio MCP. This
directory is the **wipe-box host process** layer. Seats still talk to the
SQLite file through wrappers (`docs/studio/TASKBOARD.md`). Agent Kanban
(`ak`, AMA, `scripts/studio/agent-kanban/`) stays gone.

Do not vendor the `taskboard` binary into git.

## After a machine wipe

From a grok-cloud-studio checkout (see `docs/studio/WIPE.md`):

```bash
# 1. Binary (brew tap, else GitHub release tarball — do not compile)
bash scripts/studio/taskboard/install-taskboard.sh

# 2. UI on 127.0.0.1:3010  (DB $GCS_A2A_STATE/taskboard/taskboard.db)
#    PALEMON_A2A_STATE is accepted if GCS_A2A_STATE is unset.
bash scripts/studio/taskboard/start-taskboard.sh start
bash scripts/studio/taskboard/start-taskboard.sh status

# 3. HTTP MCP on 127.0.0.1:3011  (child: taskboard --db $DB mcp)
bash scripts/studio/taskboard/mcp-http.sh start

# 4. Then the bus (NO --daemons) with GCS_MIND_SEATS from studio.env
scripts/a2a/start-studio-bus.sh start

# 5. Optional Tailscale Serve only if the node is already joined
#    PALEMON_TAILSCALE_SERVE=0 skips. Funnel stays off.
#    Host default: palemon-studio.panther-arctic.ts.net
bash scripts/studio/taskboard/start-tailscale-serve.sh start
```

Stop:

```bash
bash scripts/studio/taskboard/mcp-http.sh stop
bash scripts/studio/taskboard/start-taskboard.sh stop
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
| `PALEMON_TAILSCALE_SERVE=0` | Skip Tailscale Serve |

Never print or commit `CURSOR_API_KEY` or Tailscale auth keys.
