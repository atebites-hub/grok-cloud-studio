# Agent Kanban — studio mission control

Grok Cloud Studio mirrors Extra High fleet rows onto an [Agent Kanban](https://agent-kanban.dev) board. This is **sync-only mission control**: the local A2A bus may run a light **board-writer** that calls `fleet-bridge.py` as an observer (`ak create task` + status transitions). It does **not** start the Agent Kanban worker daemon.

Upstream CLI/source: [github.com/saltbo/agent-kanban](https://github.com/saltbo/agent-kanban). License: **FSL-1.1-ALv2**.

The local HTML dashboard under `scripts/studio/dashboard/` is **LEGACY**. Use this board instead.

## Why board-writer (ancestry)

`ak create task` / `ak auth login --leader-agent` require:

1. `CURSOR_AGENT` env set (detects runtime=`cursor`)
2. A parent process whose `ps` command matches `cursor-agent` (ancestry walk)

Machine API keys alone get **403** on task create (`agent:leader or agent:worker required`).

**Solution:** `board-writer.sh` starts one tiny long-lived process with `exec -a cursor-agent bash board-writer-loop.sh`, exports `CURSOR_AGENT=1`, runs idempotent `ak auth login --leader-agent`, then polls `fleet-bridge.py --once --force` every ≥60s.

Do **not** clobber a real `cursor-agent` under `~/.local/share/cursor-agent/versions/*/cursor-agent`. Prefer `exec -a`. Optional: `cursor-agent-shim.sh --install` (skips if a real binary exists).

**`ak start` is unsupported as a studio default** (RAM / fights Extra High). Never wire it into `start-studio-bus.sh`.

## Sync-only (do not `ak start` by default)

| Do | Do not |
|---|---|
| `ak config set`, `ak get board`, `ak create board/task`, `ak task claim/review/complete` | `ak start` / `ak stop` as part of the studio bus |
| Mirror `.a2a-state/*/fleet.jsonl` (+ events) → AK Tasks via board-writer | Claim studio seats or spawn AK workers from this repo |
| Keep keys out of logs and git | Print `AGENT_KANBAN_API_KEY` / `GCS_AGENT_KANBAN_API_KEY` |

## Environment

Primary names are `AGENT_KANBAN_*`. Grok Cloud Studio aliases are `GCS_AGENT_KANBAN_*` / `GCS_AK_*`.

| Variable | Alias | Purpose |
|---|---|---|
| `AGENT_KANBAN_API_KEY` | `GCS_AGENT_KANBAN_API_KEY` | Machine API key (never print / never commit) |
| `AGENT_KANBAN_API_URL` | `GCS_AGENT_KANBAN_API_URL` | Default `https://agent-kanban.dev` |
| `AGENT_KANBAN_BOARD_NAME` | `GCS_AGENT_KANBAN_BOARD_NAME` | Board title override |
| `AGENT_KANBAN_BOARD_ID` | `GCS_AGENT_KANBAN_BOARD_ID` | Skip lookup when set |
| `AGENT_KANBAN_GITHUB_REPO` | `GCS_AGENT_KANBAN_GITHUB_REPO` | Optional git remote to register |
| `AGENT_KANBAN_BIN` | `GCS_AGENT_KANBAN_BIN` | CLI name, default `ak` |
| `AGENT_KANBAN_SECRET_PATH` | `GCS_AGENT_KANBAN_SECRET_PATH` | Path or JSON blob with `api_key` |
| `AK_BRIDGE_POLL_SEC` | `GCS_AK_POLL_SEC` / `GCS_AK_BRIDGE_POLL_SEC` | Board-writer poll (floor 60s) |
| — | `GCS_AK_BRIDGE` | `1` force-on / `0` force-off bus board-writer |
| — | `GCS_AK_DRY` | Dry-run observer (no mutate) |
| — | `GCS_AK_FORCE` | Recreate `dry-*` task-map placeholders |

Key resolution for `configure-ak.sh`: `AGENT_KANBAN_API_KEY`, then `GCS_AGENT_KANBAN_API_KEY`, then connector-secrets JSON `api_key` (file or blob). Connector file default: `.a2a-state/agent-kanban/connector-secrets.json` (no private host paths in this public repo).

## Scripts

| Script | Role |
|---|---|
| `install-ak.sh` | Idempotent `ak` install |
| `configure-ak.sh` | `ak config set`; auth probe; never echoes key |
| `bootstrap-board.sh` | Ensure board + repo; write `board.id` |
| `board-writer.sh` | `start|stop|status|once` light writer (argv0=`cursor-agent`) |
| `board-writer-loop.sh` / `board-writer-once.sh` | Inner loop / one-shot |
| `cursor-agent-shim.sh` | Optional PATH shim; prefer `exec -a` |
| `fleet-bridge.py` | Upsert tasks; `--force` recreates `dry-*`; label `extra-high` only |
| `notify-event.sh` | Observer events |

### board-writer usage

```bash
export GCS_AGENT_KANBAN_BOARD_ID=<board-id>
bash scripts/studio/agent-kanban/configure-ak.sh   # expect AK_AUTH_OK
bash scripts/studio/agent-kanban/board-writer.sh once
bash scripts/studio/agent-kanban/board-writer.sh start
bash scripts/studio/agent-kanban/board-writer.sh status
```

Refuses to start when `MemAvailable` < ~2GB (`AK_WRITER_SKIP_LOW_MEM`). Direct CLI may fail ancestry — prefer board-writer.

## Studio bus

When `AGENT_KANBAN_API_KEY` / `GCS_AGENT_KANBAN_API_KEY` is set, or `.a2a-state/agent-kanban/configured` exists, or `GCS_AK_BRIDGE=1`, `scripts/a2a/start-studio-bus.sh` starts/stops/status the **board-writer**. Missing CLI or a crash is non-fatal. Status includes `board_writer=up/down`. The bus never invokes `ak start`.

## Seat lifecycle + hardening

- Seat control plane: `scripts/a2a/seat-lifecycle.sh` — see `docs/studio/a2a/SEAT_LIFECYCLE.md`
- Crash recovery checklist: `docs/studio/directors/HARDENING.md`

## Legacy dashboard

See `scripts/studio/dashboard/README.md` — LEGACY pointer back here.
