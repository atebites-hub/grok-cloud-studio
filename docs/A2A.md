# A2A bus

```bash
scripts/a2a/start-studio-bus.sh                 # hub + leftover dispatch + bot-bridge + fleet-shepherd
scripts/a2a/start-studio-bus.sh start --daemons # ACP serve + GROW wake loops + host ticker (opt-in)
scripts/a2a/send.sh ops "ping: hello"
scripts/a2a/start-studio-bus.sh status
```

`scripts/a2a/start-bus.sh` is a compatibility wrapper for the same commands.

Cards/registry: `docs/a2a/`. Runtime state lives in `.a2a-state/` (gitignored).

Hub default: `http://127.0.0.1:8732` (`GCS_A2A_HUB` / `GCS_A2A_PORT`).
Example seats: `floor`, `ops`, `cloud`, `qa-a`, `qa-b`.
ACP / GROW cap: `GCS_ACP_SEATS` / `GCS_GROW_SEATS` (default `floor,studio-ops`; `ops` aliases `studio-ops`). Mail cannot auto-start seats outside that allowlist. `skipSeats` stay skipped. See `docs/studio/GROK_LEADER.md`.

## GROW wake (Bot-equivalent host OS)

xAI grok-build does not accept external PRs, so `deliver_wake()` cannot live inside `grok agent serve`. Closest Bot-equivalent host OS:

1. One persistent `grok agent serve` per seat (`scripts/directors/start-seat-daemon.sh`).
2. GROW wake: `inbox.jsonl` growth → `scripts/a2a/wake-daemon.py` → `scripts/directors/seat-prompt-acp.sh` → `session/prompt` **inside that serve pid** (never `grok --resume`).
3. Pin-session: reuse `.a2a-state/<seat>/acp.session`. Do not remint per ping.
4. Named identity: `docs/studio/directors/souls/<seat>/{SOUL.md,MEMORY.md}` plus `GROK_MEMORY=1` on serve.
5. Host ticker (`scripts/a2a/host-ticker.py`, interval `GCS_TICKER_SEC` default 600s) enqueues `ACP_PING STATUS/CONTINUE` **work turns** (tools allowed). Not PONG. Not a 45s central assigner. Not a LAUNCH kind.

Dispatch **does not own GROW inboxes** (`DISPATCH_SKIP reason=wake-owns-inbox`). A live `wake.pid` also skips leftover inject. Do **not** advance `dispatch.offset` on those skips (wake consumes `wake.offset`).

Non-GROW seats may still use leftover `acp_inject.py` (no `--pin-session`).

## Leftover ACP / pin-session rules

`scripts/directors/acp_inject.py --pin-session` (GROW):

- **HANDOFF** only after this-prompt STATUS or a this-prompt real work tool (`ticket move` / `ticket create` / `tb move|create`, `send.sh` / A2A `message:send`, `scripts/launch-cloud-extra-high.sh`). Listing or reading a path that contains `taskboard` is not work. Shell `ls` / `cat` / `rg` of a path containing `launch-cloud-extra-high.sh` or `send.sh` is not work — match the invoked argv, not a flattened payload blob. Log `ACP_INJECT_HANDOFF reason=status` or `reason=work`. **Never** `reason=queue,tool,harvest`. **Never** `reason=substantial`. **Never** 1s silence. **Never** `x.ai/queue/changed` alone. Keep-alive acknowledgements (`Keep-alive received. Scanning A2A inboxes, fleet ledgers`, len>=40) are a start, not a leave. Leftover harvest (queue + leftover tools + short text) is a start, not a leave.
- If the actor **did** start (this-prompt tool or non-RESULT update): **stay connected** until STATUS / this-prompt work tool or `session/prompt` RPC completes **with STATUS**. First tool + short text is **not** a reason to hang up. Accept is not a reason to hang up.
- Dead session: after N consecutive no-start nacks (`GCS_ACP_DEAD_STREAK`, default 3) with no chunks / no tools within `GCS_ACP_ACCEPT_DEADLINE` (default 120s), **one** `session/new`. Log `ACP_INJECT_SESSION_DEAD`. Clear the streak on real work. Silence / queue-only is `ACP_INJECT_TIMEOUT reason=no-accept`, not HANDOFF. 30s of silence is not leave. If the actor started (any accept signal), stay until STATUS/work or `session/prompt` RPC, up to `GCS_ACP_INJECT_TIMEOUT` (default 180s). Do not remint a started turn.
- **RESULT is duplex, not success.** Leftover tools + empty text is not work. RESULT-only is `reason=hangup-only`. Do **not** `session/cancel` a live turn you handed off.
- Authenticate ACP `cached_token` after initialize. Copy host `~/.grok/auth.json` into seat `GROK_HOME` (never print the token). Log `ACP_INJECT_AUTH` / `SEAT_GROK_AUTH_OK`.

Leftover dispatch (no `--pin-session`) still harvests work/STATUS and `session/cancel`s on timeout so grok 1.0.3 is not `start_blocked`.

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

Board is **tcarac/taskboard** (ticket CLI + HTTP `/mcp`). See `docs/studio/TASKBOARD.md`. Agent Kanban was removed; do not reconnect `ak`. The local HTML dashboard under `scripts/studio/dashboard/` is LEGACY.
