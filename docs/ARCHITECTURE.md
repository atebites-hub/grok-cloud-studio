# Architecture

Grok Cloud Studio is a **local control plane**:

1. **Directors** are Grok Build CLI seats (`floor`, `ops`, `cloud`, `qa-a`, `qa-b` by default). They assign work and collect PRs. They do not implement large diffs locally.
2. **Extra High grunts** are Cursor Cloud agents (`grok-4.6`, `effort=xhigh`) that open PRs against `GCS_CLOUD_REPO` / `CLOUD_REPO_URL`.
3. **A2A** is seat-to-seat. **MCP** is agent-to-tool.

```
send.sh → hub.py (ack + inbox JSONL)
            ↓
        dispatch.py  → acp_inject.py (persistent grok agent serve)
                     → launch-director.sh  (one-shot -p fallback)

launch-cloud-extra-high.sh → @cursor/sdk Agent.create
                           → spawn-waiter.sh → wait-notify.ts (run.wait)
                           → A2A ping owning seat (FLEET_DONE / PR_READY)

fleet-shepherd.py = orphan-only safety net (no live waiter_pid)
webhook_receiver.py = optional signed completion path
```

## A2A hub

Stdlib HTTP+JSON (`scripts/a2a/hub.py`):

- `GET /health` `GET /registry`
- `GET /a2a/{seat}/.well-known/agent-card.json`
- `POST /a2a/{seat}/message:send` — appends `.a2a-state/<seat>/inbox.jsonl`, returns `TASK_STATE_COMPLETED` + receipt
- tasks get/list/cancel

Default bind `127.0.0.1:8732`. Cards live in `docs/a2a/cards/`. Seats and ACP ports live in `docs/a2a/registry.json` (`scripts/a2a/lib.py` is the source of truth).

`scripts/a2a/start-studio-bus.sh` starts hub + dispatch + bot-bridge + fleet-shepherd. Pass `--daemons` (or `GCS_START_SEAT_DAEMONS=1`) to also start per-seat `grok agent serve` for seats in `GCS_ACP_SEATS` (default `floor,studio-ops` — not the full registry). Daemons are **opt-in** so a bus start does not surprise-spawn five grok processes. Optional Agent Kanban `ak-bridge` (sync-only fleet mirror) starts when configured; it never runs `ak start`. See `docs/studio/AGENT_KANBAN.md`.

Grok Bot orchestrator seats (`docs/a2a/bot-agents.json`, default seat `orchestrator`) are listed in registry `skipSeats` and are **not** ACP inject targets. Bind with `GCS_BOT_AGENT_ID` + `scripts/a2a/bind-bot-agent.sh` (also run from `install.sh`). Standing Bot routines poll `.a2a-state/<seat>/bot-wake.txt` / `bot-wake.jsonl`.

## ACP

`scripts/directors/start-seat-daemon.sh <seat>` runs `grok agent serve --no-leader` on the registry ACP port (8740+). ACP serve cannot attach to `grok agent leader` (CLI v1.0.3 exits immediately). `GROK_USE_LEADER=1` only starts `scripts/directors/start-grok-leader.sh` so one-shot `grok -p` fallbacks can share a backend. Dispatch will not auto-start seats outside `GCS_ACP_SEATS`. Secrets stay in `.a2a-state/<seat>/acp.secret` (gitignored). `acp_inject.py` opens a WebSocket session and injects EXTRA TURN text. See `docs/studio/GROK_LEADER.md`.

## Extra High

See `scripts/cloud/README.md`. Create is fail-closed without `GCS_CLOUD_REPO` / `CLOUD_REPO_URL`. Auth is `CURSOR_API_KEY` (never printed). SDK-first; REST curl when `CURSOR_API_BASE` is set, `CLOUD_FORCE_REST=1`, or SDK bootstrap exits 75.

## Completion paths

| Path | When |
|---|---|
| Waiter | Default after launch (`GCS_SPAWN_WAITER` not `0`) |
| Webhook | `GCS_WEBHOOK_SECRET` set and `webhook-harness.sh serve` |
| Shepherd | Ledger row is an **orphan** (no live waiter, never notified by waiter/webhook) |

Do not double-notify a live waiter.

## Prompts

Generic seat prompts in `prompts/`. Common Director footer: `scripts/directors/common_footer.txt`.
