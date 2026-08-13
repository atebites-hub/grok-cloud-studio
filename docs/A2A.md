# A2A bus

```bash
scripts/a2a/start-studio-bus.sh                 # hub + dispatch + bot-bridge + fleet-shepherd
scripts/a2a/start-studio-bus.sh start --daemons # also ACP daemons (opt-in)
scripts/a2a/send.sh ops "ping: hello"
scripts/a2a/start-studio-bus.sh status
```

`scripts/a2a/start-bus.sh` is a compatibility wrapper for the same commands.

Cards/registry: `docs/a2a/`. Runtime state lives in `.a2a-state/` (gitignored).

Hub default: `http://127.0.0.1:8732` (`GCS_A2A_HUB` / `GCS_A2A_PORT`).
Example seats: `floor`, `ops`, `cloud`, `qa-a`, `qa-b`.

## Inject timeout + dispatch lock TTL

`acp_inject.py` defaults to **180s** (`GCS_ACP_INJECT_TIMEOUT`). On `session/prompt` timeout/failure it best-effort sends ACP `session/cancel`, writes `acp.inject.stale` (next inject auto force-new session), and exits non-zero. Dispatch lock TTL defaults to **240s** (`GCS_DISPATCH_LOCK_TTL_SEC`). If a lock pid is still alive past TTL, dispatch logs `DISPATCH_LOCK_TTL_KILL`, SIGTERM then SIGKILL that pid, clears the lock, and continues the inbox. Inject launches use `--timeout min(inject_timeout, lock_ttl-30)` so inject dies before the TTL killer races it. A mid-turn inject holding the lock for 10–15+ minutes is a bug we kill.

## Grok Bot seats (orchestrator)

Grok **Bot** agents are not `grok agent serve` / ACP inject targets. Put Bot seats in `docs/a2a/registry.json` `skipSeats` (`orchestrator` is the default example; `donald` stays in skipSeats for back-compat) and map them in `docs/a2a/bot-agents.json`.

Bind your Bot id (idempotent; never prints the full agent id):

```bash
export GCS_BOT_AGENT_ID='your-grok-bot-agent-id'
export GCS_BOT_SEAT=orchestrator   # optional; default
./install.sh                      # or: scripts/a2a/bind-bot-agent.sh
```

`./doctor.sh` **FAIL**s if any bot seat `agentId` is empty or `REPLACE_WITH_YOUR_GROK_BOT_AGENT_ID`, unless `GCS_BOT_BIND_OPTIONAL=1` (CI clone checks). Local bind state is gitignored `.a2a-state/bot-bind.json`.

`start-studio-bus.sh` starts `scripts/a2a/bot-bridge.py`, which polls Bot inboxes and writes `.a2a-state/<seat>/bot-wake.jsonl` + latest `bot-wake.txt` (offset: `bot-bridge.offset`). Logs `BOT_BRIDGE_WAKE seat=… task=…` (never secrets). Optional `BOT_BRIDGE_HOOK` for a local wake command.

Standing Bot routine (short prompt):

```text
Poll `.a2a-state/orchestrator/bot-wake.txt` and `.a2a-state/orchestrator/bot-wake.jsonl`.
When a new wake appears, read the task and act as orchestrator.
Reply via `scripts/a2a/send.sh <seat> "…"`. This seat is NOT an ACP inject target.
```

Directors use `scripts/a2a/send.sh orchestrator "…"` like any seat (`send.sh donald` still works if you keep that seat name). Do not launch Bot CloudAgent for this path.

Optional **Agent Kanban** fleet-bridge (sync-only, never `ak start`) starts when `AGENT_KANBAN_API_KEY` / `GCS_AGENT_KANBAN_API_KEY` is set or `.a2a-state/agent-kanban/configured` exists. See `docs/studio/AGENT_KANBAN.md`. The local HTML dashboard under `scripts/studio/dashboard/` is LEGACY.
