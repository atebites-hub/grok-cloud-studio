# A2A bus

```bash
scripts/a2a/start-studio-bus.sh                 # hub + leftover dispatch + shepherd
                                                # bot-bridge only if GCS_BOT_BRIDGE=1
scripts/a2a/start-studio-bus.sh start --daemons # ACP serve + GROW wake loops + host ticker (opt-in)
scripts/a2a/send.sh ops "ping: hello"           # TASK_STATE_SUBMITTED until mind finishes; ACK is a receipt, not mind-turn done
scripts/a2a/start-studio-bus.sh status
```

`scripts/a2a/start-bus.sh` is a compatibility wrapper for the same commands.

Cards/registry: `docs/a2a/`. Runtime state lives in `.a2a-state/` (gitignored).

Hub default: `http://127.0.0.1:8732` (`GCS_A2A_HUB` / `GCS_A2A_PORT`).
Example seats: `floor`, `ops`, `cloud`, plus Palemon-floor first-class
`floor-ops`, `studio-ops`, `art`, `content`, `systems`, `qa-a`, `qa-b`,
`audio`, `narrative`.
ACP / GROW cap: `GCS_ACP_SEATS` / `GCS_GROW_SEATS` (default `floor,studio-ops`; `ops` aliases `studio-ops`). Mail cannot auto-start seats outside that allowlist. `skipSeats` stay skipped. See `docs/studio/GROK_LEADER.md`.
Opt-in mind: `GCS_MIND_SEATS` (default empty, example `floor,ops`) starts `seat-mind-loop.sh` / `mind.py`. See `docs/studio/MIND.md`.

## GROW wake (leftover host OS)

xAI grok-build does not accept external PRs, so `deliver_wake()` cannot live inside `grok agent serve`. Closest leftover host OS (ACP inject):

1. One persistent `grok agent serve` per seat (`scripts/directors/start-seat-daemon.sh`).
2. GROW wake: `inbox.jsonl` growth → `scripts/a2a/wake-daemon.py` → `scripts/directors/seat-prompt-acp.sh` → `session/prompt` **inside that serve pid** (never `grok --resume`). Wake treats serve as healthy only when `daemon.pid` is alive, the `acp.url` port accepts TCP, **and that pid (or a descendant) owns the listen socket**. A leftover live `daemon.pid` plus some other listener is not this seat's serve. If serve is down or the pid does not own listen, evict the foreign listener on this seat's ACP port and restart serve — never fall back to `grok --resume`.
3. Pin-session: reuse `.a2a-state/<seat>/acp.session`. Do not remint per ping.
4. Named identity: `docs/studio/directors/souls/<seat>/{SOUL.md,MEMORY.md}` plus `GROK_MEMORY=1` on serve.
5. Host ticker (`scripts/a2a/host-ticker.py`, interval `GCS_TICKER_SEC` default 600s) enqueues `ACP_PING STATUS/CONTINUE` **work turns** (tools allowed). Not PONG. Not a 45s central assigner. Not a LAUNCH kind.

Dispatch **does not own GROW inboxes** (`DISPATCH_SKIP reason=wake-owns-inbox`). A live `wake.pid` also skips leftover inject. Do **not** advance `dispatch.offset` on those skips (wake consumes `wake.offset`). Mind seats (`GCS_MIND_SEATS` plus a live `mind/pid`) skip leftover inject (`DISPATCH_SKIP reason=mind-owns-inbox`). Dispatch re-reads `mind_seats()` on each poll. `start-studio-bus.sh start` recycles leftover dispatch only when `.a2a-state/dispatch.mind-seats` differs from the current env / `studio.env` set; a match keeps `STUDIO_BUS_DISPATCH_ALREADY`. Recycle does not kill hub, fleet-shepherd, seat minds, host ticker, or `grok agent serve`. Default-off `start` / `recover.sh` evict leftover live `bot-bridge.pid` (`STUDIO_BUS_BOT_BRIDGE_ALREADY` only when `GCS_BOT_BRIDGE=1`; do not remint that live pid). `start` / `recover.sh` do not spawn bot-bridge unless `GCS_BOT_BRIDGE=1`.

Non-GROW seats may still use leftover `acp_inject.py` (no `--pin-session`).

## Seat mind (Bot-equivalent)

`GCS_MIND_SEATS` (default empty, example `floor,ops`) starts `scripts/directors/seat-mind-loop.sh` → `scripts/directors/mind.py`. Python is mailbox + pin + stay-up: inbox growth → one `grok --resume` (first turn `--session-id`) of a UUID in `$GCS_A2A_STATE/<seat>/mind/session` with `--prompt-file` (never bare `-p`) → persist `transcript.jsonl` / `offset` (offset only on grok/cursor runner exit 0). Hub `TASK_STATE_COMPLETED` / A2A ACK is a receipt, not mind-turn done. Harvest writes `mind/mail.txt` and Bot-like `mind/turn.txt` **before** the runner. `seat-mind-loop.sh` installs grok `plugin.json` plugins `studio-mind`, `a2a`, and `cursor-cloud` into seat `GROK_HOME` via `install_mind_grok_plugins` (`grok plugin install --trust`; not Hermes `plugin.yaml`; do not vendor hermes-agent) and remaining spawn PATH wrappers (`cloud_launch`, `a2a_send`) via `scripts/a2a/mind_bot_like.py install-spawn`. Extra High spawn execs `scripts/launch-cloud-extra-high.sh` or `cloud_launch` (never `grok --resume` for Cloud create; never Bot CloudAgent). (`--plugin-dir` is a grok agent flag, not headless). No ACP WebSocket, no leftover pin-session. Mind is the GROW path when opted in; ACP wake is skipped for those seats unless `GCS_MIND_PLUS_ACP_WAKE=1`. Host ticker includes `GCS_MIND_SEATS` as mailbox keep-alives even without `--daemons`. Do not kill existing serve. `skipSeats` (orchestrator, donald) are not mind seats. See `docs/studio/MIND.md`, `tests/features/liv63_mind_bot_like.feature`, and `tests/features/liv63_mind_plugins.feature`.

## Leftover ACP / pin-session rules

`scripts/directors/acp_inject.py --pin-session` (GROW):

- **HANDOFF** only after this-prompt STATUS or a this-prompt real work tool (`ticket move` / `ticket create` / `tb move|create`, `send.sh` / A2A `message:send`, `scripts/launch-cloud-extra-high.sh`). Listing or reading a path that contains `taskboard` is not work. Shell `ls` / `cat` / `rg` of a path containing `launch-cloud-extra-high.sh` or `send.sh` is not work — match the invoked argv, not a flattened payload blob. Log `ACP_INJECT_HANDOFF reason=status` or `reason=work`. **Never** `reason=queue,tool,harvest`. **Never** `reason=substantial`. **Never** 1s silence. **Never** `x.ai/queue/changed` alone. Keep-alive acknowledgements (`Keep-alive received. Scanning A2A inboxes, fleet ledgers`, any length) are a start, not a leave. Leftover harvest (queue + leftover tools + short text) is a start, not a leave.
- If the actor **did** start (any accept signal): **stay connected** until STATUS / this-prompt work tool or the full inject timeout. First tool + short text is **not** a reason to hang up. Accept is not a reason to hang up. Do **not** remint a started turn.
- Dead session: after N consecutive no-start nacks (`GCS_ACP_DEAD_STREAK`, default 3) with no chunks / no tools within `GCS_ACP_ACCEPT_DEADLINE` (default 120s), **one** `session/new`. Log `ACP_INJECT_SESSION_DEAD`. Clear the streak on real work. First no-accept does **not** remint. Silence / queue-only is `ACP_INJECT_TIMEOUT reason=no-accept`, not HANDOFF. 30s of silence is not leave. If the actor started (any accept signal), stay until STATUS/work or timeout, up to `GCS_ACP_INJECT_TIMEOUT` (default 180s). These defaults live in `acp_inject.py` (the law), not a live `studio.env` overlay. Wake wrapper `GCS_WAKE_ACP_TIMEOUT` default 600s.
- **RESULT is duplex, not success.** Leftover tools + empty text is not work. RESULT-only is `reason=hangup-only`. RESULT-only / PONG is a bug. Directors print `RESULT bc-id=<id or none> pr=<url or none> a2a=<task-id or none> notes=<one line>`; duplex writes that line onto the A2A task and may ping the caller. Hub `TASK_STATE_COMPLETED` / A2A ACK is a protocol receipt, not mind-turn done, not this RESULT line. Do **not** `session/cancel` a live turn you handed off.
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

`start-studio-bus.sh` starts `scripts/a2a/bot-bridge.py` **only when `GCS_BOT_BRIDGE=1`**. Default off: Bot seats stay standby. A leftover live `bot-bridge.pid` is not a default start — recover/start evict it unless opted in. Opt-in keep is `STUDIO_BUS_BOT_BRIDGE_ALREADY` (same pid; do not remint). The bridge polls Bot inboxes and writes `.a2a-state/<seat>/bot-wake.jsonl` + latest `bot-wake.txt` (offset: `bot-bridge.offset`). Logs `BOT_BRIDGE_WAKE seat=… task=…` (never secrets). Optional `BOT_BRIDGE_HOOK` for a local wake command. `recover.sh` / `start` do not start the bridge unless that env is set.

Standing Bot routine (short prompt):

```text
Poll `.a2a-state/orchestrator/bot-wake.txt` and `.a2a-state/orchestrator/bot-wake.jsonl`.
When a new wake appears, read the task and act as orchestrator.
Reply via `scripts/a2a/send.sh <seat> "…"`. This seat is NOT an ACP inject target.
```

Directors use `scripts/a2a/send.sh orchestrator "…"` like any seat (`send.sh donald` still works if you keep that seat name **and** a donald Agent Card exists). Do not launch Bot CloudAgent for this path.

## Duplex RESULT notify (skipSeats)

`scripts/a2a/duplex.py` writes Director `RESULT` onto the working seat's A2A task and may ping the caller with `A2A_REPLY`. That ping must succeed after RESULT and must not 404.

`donald` is a skipSeat with no shipped Agent Card (not an ACP inject target). Duplex maps `donald` → `floor-ops` (Palemon Donald-clone Director), then `orchestrator` (Bot card). A fallback equal to the working seat is skipped (if `floor-ops` produced the RESULT, ping `orchestrator` instead of self). If neither card exists, **skip notify** (`notify_skipped=skipSeat`) without failing the task reply (`ok` stays true; `director-result` is still stored). A failed `send.sh` is `notify_skipped=send-fail`, still not a failed task reply. A caller with no Agent Card and no skipSeat fallback is `notify_skipped=no-card`.

Hub enqueue is `TASK_STATE_SUBMITTED` until mind harvests (LIV-85). Later `TASK_STATE_COMPLETED` / `send.sh` `A2A_SEND_OK` is a protocol **receipt**, not mind-turn done — not Director RESULT and not proof the seat acted. This is not a LIV-85 clone. `donald` / `orchestrator` stay `skipSeats`.

## CCGS leads (mind seats)

Role map onto first-class GCS seats. Do not mint 49 specialist seats.
Directors and leads spawn specialists only via `scripts/launch-cloud-extra-high.sh`.

| CCGS lead | GCS seat |
|---|---|
| producer | `floor-ops` |
| creative | `floor` |
| technical | `systems` |
| game-designer | `content` |
| lead-programmer | `systems` (until split) |
| art-director | `art` |
| qa-lead | `qa-a` |
| release-manager | `studio-ops` |
| audio | `audio` |
| narrative | `narrative` |

`audio` and `narrative` are first-class registry seats. The other titles are
aliases (`scripts/a2a/lib.py` `CCGS_LEAD_ALIASES`). `python3 scripts/a2a/lib.py known
producer` prints `floor-ops`. Unmapped specialist titles (`composer`,
`narrative-designer`, …) do not mint seats: `known` exits 1, and
`mind-seats` / `grow-seats` / `launch-seats` / the host ticker drop them.
FAT: [`tests/features/ccgs_audio_narrative_map.feature`](../tests/features/ccgs_audio_narrative_map.feature).
Distinct from LIV-41 mind-must-launch clones.

Board is **tcarac/taskboard** (ticket CLI + HTTP `/mcp`). See `docs/studio/TASKBOARD.md`. Agent Kanban was removed; do not reconnect `ak`. The local HTML dashboard under `scripts/studio/dashboard/` is LEGACY.
