# Architecture

Grok Cloud Studio is a **local control plane**:

1. **Directors** are Grok Build CLI seats (`floor`, `ops`/`studio-ops`, `cloud`,
   `floor-ops`, `art`, `content`, `systems`, `qa-a`, `qa-b`, `audio`,
   `narrative`). They assign work
   and collect PRs. They do not implement large diffs locally. Crash-safe ACP
   cap is `GCS_ACP_SEATS` (default `floor,studio-ops`). Palemon wipe: `docs/studio/WIPE.md`.
   CCGS leads: producer=`floor-ops`, creative=`floor`, technical=`systems`,
   game-designer=`content`, lead-programmer=`systems` until split,
   art-director=`art`, qa-lead=`qa-a`, release-manager=`studio-ops`,
   plus first-class `audio` and `narrative`. Do not add 49 specialists.
   Spawn specialists only via `scripts/launch-cloud-extra-high.sh`.
   List Extra High by `runStatus=RUNNING`, not leftover agent `status=ACTIVE`.
2. **Extra High grunts** are Cursor Cloud agents (`grok-4.6`, `effort=xhigh`) that open PRs against `GCS_CLOUD_REPO` / `CLOUD_REPO_URL`.
3. **A2A** is seat-to-seat. **MCP** is agent-to-tool.

```
send.sh → hub.py (ack + inbox JSONL)
            ↓
        mind.py         → grok --resume pinned UUID --prompt-file   (GCS_MIND_SEATS)
        wake-daemon.py  → seat-prompt-acp.sh --pin-session  (GROW seats, leftover)
        dispatch.py     → leftover acp_inject.py            (non-GROW only)
                        → launch-director.sh  (one-shot -p fallback)

host-ticker.py → ACP_PING STATUS/CONTINUE inbox lines (work turns, tools allowed)

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

`scripts/a2a/start-studio-bus.sh` starts hub + leftover dispatch + bot-bridge + fleet-shepherd. Pass `--daemons` (or `GCS_START_SEAT_DAEMONS=1`) to also start per-seat `grok agent serve` for seats in `GCS_ACP_SEATS` (default `floor,studio-ops` — not the full registry), GROW `seat-wake-loop.sh` / `wake-daemon.py`, and `host-ticker.py`. Set `GCS_MIND_SEATS` (example `floor,ops`) to start `seat-mind-loop.sh` / `mind.py` instead of ACP wake for those seats (`GCS_MIND_PLUS_ACP_WAKE=1` to run both). Mind does not kill existing serve. `start` recycles leftover dispatch only when `.a2a-state/dispatch.mind-seats` differs from the current env / `studio.env` set; a match keeps `STUDIO_BUS_DISPATCH_ALREADY`. Recycle does not kill hub, bot-bridge, fleet-shepherd, seat minds, host ticker, or serve. See `docs/studio/MIND.md`. Daemons are **opt-in** so a bus start does not surprise-spawn grok processes. Agent Kanban was removed; the board is tcarac/taskboard (`docs/studio/TASKBOARD.md`).

Grok Bot orchestrator seats (`docs/a2a/bot-agents.json`, default seat `orchestrator`) are listed in registry `skipSeats` and are **not** ACP inject targets. Bind with `GCS_BOT_AGENT_ID` + `scripts/a2a/bind-bot-agent.sh` (also run from `install.sh`). Standing Bot routines poll `.a2a-state/<seat>/bot-wake.txt` / `bot-wake.jsonl`.

## ACP

`scripts/directors/start-seat-daemon.sh <seat>` runs `grok agent serve --no-leader` on the registry ACP port (8740+) with `GROK_MEMORY=1` and named identity (`SOUL.md`). ACP serve cannot attach to `grok agent leader` (CLI v1.0.3 exits immediately). `GROK_USE_LEADER=1` only starts `scripts/directors/start-grok-leader.sh` so one-shot `grok -p` fallbacks can share a backend. Dispatch will not auto-start seats outside `GCS_ACP_SEATS` and does not ACP-inject GROW inboxes. Secrets stay in `.a2a-state/<seat>/acp.secret` (gitignored). GROW pin-session inject stays on the websocket until STATUS/work-tool (argv) or timeout; leftover dispatch still harvests then `session/cancel`s. See `docs/A2A.md` and `docs/studio/GROK_LEADER.md`.

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

Generic seat prompts ship in `prompts/`. Product floors keep `*_director_prompt.txt` under `docs/studio/directors/`. `GCS_PROMPT_DIR` / `PROMPTS_DIR` override the default directory. When `$ROOT/prompts` is missing or has no `*_director_prompt.txt` files, daemons default to `$ROOT/docs/studio/directors`. `write_agent_profile` / `launch-director.sh` resolve `${seat}_director_prompt.txt` from either layout (including `floor_ops_director_prompt.txt`) so remint does not fail when only the docs tree is populated. `install.sh` links docs files into `prompts/` when missing.

Common Director footer: `scripts/directors/common_footer.txt`.
