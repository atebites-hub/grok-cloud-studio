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
   plus first-class `audio` and `narrative` (aliases: audio-director,
   audio-lead, narrative-director, narrative-lead). Do not add 49 specialists.
   Spawn specialists only via `scripts/launch-cloud-extra-high.sh`.
2. **Extra High grunts** are Cursor Cloud agents (`grok-4.6`, `effort=xhigh`) that open PRs against `GCS_CLOUD_REPO` / `CLOUD_REPO_URL`.
3. **A2A** is seat-to-seat. **MCP** is agent-to-tool.

```
send.sh → hub.py (enqueue SUBMITTED + inbox JSONL; ACK is a receipt, not mind-turn done)
            ↓
        mind.py         → grok --resume pinned UUID --prompt-file; auto mind/runner; 402 MIND_SWITCH once
                        → COMPLETED only after harvest + runner exit 0 (still a receipt)
        wake-daemon.py  → seat-prompt-acp.sh --pin-session  (GROW seats, leftover)
        dispatch.py     → leftover acp_inject.py            (non-GROW only)
                        → launch-director.sh  (one-shot -p fallback)

host-ticker.py → ACP_PING STATUS/CONTINUE inbox lines (work turns, tools allowed; not PONG; not a LAUNCH kind)

launch-cloud-extra-high.sh → @cursor/sdk Agent.create
                           → spawn-waiter.sh → wait-notify.ts (GET latest runStatus)
                           → A2A ping owning seat + REPORT_TO (default studio-ops)
                           leftover FINISHED is not done while a newer run is CREATING/RUNNING
                           CANCELLED latest + prUrl → FLEET_DONE / INSPECT (not MERGE_REQUEST)

fleet-shepherd.py = orphan-only Extra High safety net (no live waiter_pid; dead waiter_pid is evicted);
                    also TASKBOARD_HEALTH_OK / TASKBOARD_HEALTH_FAIL
Host board maintainer kit = scripts/studio/taskboard/maintainer.sh (start/health/docs); not shepherd, not seat MCP
webhook_receiver.py = optional signed completion path
```

## A2A hub

Stdlib HTTP+JSON (`scripts/a2a/hub.py`):

- `GET /health` `GET /registry`
- `GET /a2a/{seat}/.well-known/agent-card.json`
- `POST /a2a/{seat}/message:send` — appends `.a2a-state/<seat>/inbox.jsonl`, returns `TASK_STATE_SUBMITTED` (queued until mind harvests and finishes). A2A ACK / `kind=receipt` is a receipt, not mind-turn done. Later `TASK_STATE_COMPLETED` is still a protocol receipt, not `MIND_TURN`. Duplex `A2A_REPLY` maps skipSeat `donald` → `floor-ops` / `orchestrator` so notify does not 404; a missed ping does not fail the task reply.
- tasks get/list/cancel

Default bind `127.0.0.1:8732`. Cards live in `docs/a2a/cards/`. Seats and ACP ports live in `docs/a2a/registry.json` (`scripts/a2a/lib.py` is the source of truth).

`scripts/a2a/start-studio-bus.sh` starts hub + leftover dispatch + fleet-shepherd. **bot-bridge is opt-in** (`GCS_BOT_BRIDGE=1`); Bot seats stay standby otherwise. Pass `--daemons` (or `GCS_START_SEAT_DAEMONS=1`) to also start per-seat `grok agent serve` for seats in `GCS_ACP_SEATS` (default `floor,studio-ops` — not the full registry), GROW `seat-wake-loop.sh` / `wake-daemon.py`, and `host-ticker.py`. Set `GCS_MIND_SEATS` (example `floor,ops`) to start `seat-mind-loop.sh` / `mind.py` instead of ACP wake for those seats (`GCS_MIND_PLUS_ACP_WAKE=1` to run both). Mind does not kill existing serve. `start` recycles leftover dispatch only when `.a2a-state/dispatch.mind-seats` differs from the current env / `studio.env` set; a match keeps `STUDIO_BUS_DISPATCH_ALREADY`. Recycle does not kill hub, fleet-shepherd, seat minds, host ticker, or serve. Default-off start/recover evict leftover live `bot-bridge.pid` (`ALREADY` only when `GCS_BOT_BRIDGE=1`; do not remint). See `docs/studio/MIND.md`. Huge `inbox.jsonl` files compact in place (`rotate_inbox` in `scripts/a2a/lib.py`) so leftover dispatch and mind harvest do not reread consumed megabyte prefixes; unread lines stay and `wake.offset` / `mind/offset` stay consistent. Daemons are **opt-in** so a bus start does not surprise-spawn grok processes. Agent Kanban was removed; the board is tcarac/taskboard (`docs/studio/TASKBOARD.md`). `start-studio-bus.sh start`, `recover.sh`, and `doctor.sh` refuse `PALEMON_AK_BRIDGE` and never exec leftover `ak` / AMA.

Director RESULT is duplex, not success: print `RESULT bc-id=<id or none> pr=<url or none> a2a=<task-id or none> notes=<one line>`; `scripts/a2a/duplex.py` writes it onto the A2A task. RESULT-only / PONG is a bug. Never launch Bot CloudAgent. Hub enqueue is `TASK_STATE_SUBMITTED` (queued until mind harvests); later `TASK_STATE_COMPLETED` is still a protocol receipt, not mind-turn done, not that RESULT line.

Grok Bot orchestrator seats (`docs/a2a/bot-agents.json`, default seat `orchestrator`) are listed in registry `skipSeats` and are **not** ACP inject targets. Bind with `GCS_BOT_AGENT_ID` + `scripts/a2a/bind-bot-agent.sh` (also run from `install.sh`). Standing Bot routines poll `.a2a-state/<seat>/bot-wake.txt` / `bot-wake.jsonl`. Extra High `--name` matching a Bot skipSeat is refused (never Bot CloudAgent).

## ACP

`scripts/directors/start-seat-daemon.sh <seat>` runs `grok agent serve --no-leader` on the registry ACP port (8740+) with `GROK_MEMORY=1` and named identity (`SOUL.md`). ACP serve cannot attach to `grok agent leader` (CLI v1.0.3 exits immediately). `GROK_USE_LEADER=1` only starts `scripts/directors/start-grok-leader.sh` so one-shot `grok -p` fallbacks can share a backend. Dispatch will not auto-start seats outside `GCS_ACP_SEATS` and does not ACP-inject GROW inboxes. Secrets stay in `.a2a-state/<seat>/acp.secret` (gitignored). GROW pin-session inject stays on the websocket until STATUS/work-tool (argv) or timeout; leftover dispatch still harvests then `session/cancel`s. See `docs/A2A.md` and `docs/studio/GROK_LEADER.md`.

## Extra High

See `scripts/cloud/README.md`. Create is fail-closed without `GCS_CLOUD_REPO` / `CLOUD_REPO_URL`. Auth is `CURSOR_API_KEY` (never printed). SDK-first; REST curl when `CURSOR_API_BASE` is set, `CLOUD_FORCE_REST=1`, or SDK bootstrap exits 75.

MERGE_REQUEST / QA squash requires pasted `.venv/bin/pytest -q` (`N passed`) and `python3 scripts/secret_scan.py` (`secret_scan=clean`). Empty GitHub leftover-green is not a ship-gate. `scripts/cloud/pr_evidence.py judge` is the verdict. FLEET_DONE HOLDs PRs without that paste.

## Completion paths

| Path | When |
|---|---|
| Waiter | Default after launch (`GCS_SPAWN_WAITER` not `0`). Empty GitHub checks (`check_runs=0`) are not MERGE_REQUEST-ready. MERGEABLE+empty CI is leftover-green theatre. Latest run `CANCELLED` with `prUrl` pings `INSPECT follow-up-or-close` (not MERGE_REQUEST). |
| Webhook | `GCS_WEBHOOK_SECRET` set and `webhook-harness.sh serve` |
| Shepherd | Ledger row is an **orphan** (no live waiter, never notified by waiter/webhook). Dead `waiter_pid` is evicted on `fleet.jsonl` before notify-once. |

Each shepherd cycle also probes tcarac/taskboard: the SQLite DB file
(`GCS_TASKBOARD_DB` or `$GCS_A2A_STATE/taskboard/taskboard.db`) plus
`taskboard --db $DB ticket list` **or** HTTP `POST /mcp`. It logs
`TASKBOARD_HEALTH_OK` or `TASKBOARD_HEALTH_FAIL`. GET `/health` alone is
not enough. The probe does not start the board, skip leftover shells,
install seat stdio MCP, or reconnect Agent Kanban.

Do not double-notify a live waiter. A leftover `waiter_pid` number is not liveness.

`python3 scripts/cloud/fleet_ledger.py prune` drops leftover `fleet.jsonl` rows that are already closed (`notified`, `status=closed`, latest run `FINISHED|ERROR|CANCELLED|EXPIRED`). Open leftover shells stay. Ledger-only; no Cloud probe.

## Linear (Living Sky)

Free-tier **200**-issue cap (LIV-76): close stale Living Sky tickets and
archive Done/Canceled via GraphQL `scripts/linear_archive_closed.py`. Do **not**
delete (`issueDelete` / GCS #45 purge is the wrong mechanic). Linear MCP has no
archive mutation. Never Black Swan Money. Operator notes: `docs/studio/LINEAR.md`.

## Prompts

Generic seat prompts ship in `prompts/`. Product floors keep `*_director_prompt.txt` under `docs/studio/directors/`. `GCS_PROMPT_DIR` / `PROMPTS_DIR` override the default directory. When `$ROOT/prompts` is missing or has no `*_director_prompt.txt` files, daemons default to `$ROOT/docs/studio/directors`. `write_agent_profile` / `launch-director.sh` resolve `${seat}_director_prompt.txt` from either layout (including `floor_ops_director_prompt.txt`) so remint does not fail when only the docs tree is populated. `install.sh` links docs files into `prompts/` when missing.

Common Director footer: `scripts/directors/common_footer.txt`. Every mind turn, after real evidence, stamps Living Sky Linear (`LIV-*`) via `save_comment`. Extra High is the grok-4.6 xhigh effort pin for Cursor Cloud specialists, not a product name. Spawn via `scripts/launch-cloud-extra-high.sh`.
