# Grok agent leader (shared backend)

## Why

Each `grok agent serve --no-leader` is a fat process (~100-160MB). Spawning
every registry seat as a persistent ACP daemon OOMs a ~15GB studio box and
crashes the VM.

`grok agent leader` is a **process multiplexer**: one shared backend, many
clients connect with `grok agent --leader`. This is **not** the Agent Kanban
"leader agent" concept.

## Hard CLI fact (v1.0.3)

`grok agent --leader serve` **exits immediately**. ACP WebSocket seats cannot
share the leader. Persistent Directors stay `--no-leader serve`. The leader is
for one-shot `grok -p` / `grok agent --leader` fallbacks so those do not fork
more fat backends.

## Studio defaults (15GB)

`.a2a-state/studio.env` (local, not committed):

```bash
GCS_ACP_SEATS=floor,studio-ops
GROK_USE_LEADER=0
```

The GCS example registry names the ops seat `ops`. Bus/dispatch treat
`studio-ops` as an alias for `ops` when `ops` is in `launch-seats`.

- `GCS_ACP_SEATS` caps which seats the bus starts **and** which seats
  `dispatch.py` may auto-respawn. Crash recovery must never bring back the
  full registry as `serve` processes. `skipSeats` (Bot orchestrator, etc.)
  are never ACP inject targets.
- Keep at most two ACP serve processes on this box (floor + ops / studio-ops).
- Run `scripts/directors/start-grok-leader.sh` so `-p` fallbacks can attach.

Also set `[cli] use_leader = true` in `~/.grok/config.toml` (local only) so
top-level `grok -p` attaches to the leader instead of spawning a backend.

## Commands

```bash
bash scripts/directors/start-grok-leader.sh
bash scripts/directors/status-grok-leader.sh
bash scripts/a2a/start-studio-bus.sh start --daemons
bash scripts/directors/start-seat-daemon.sh studio-ops
python3 scripts/a2a/wake-daemon.py --seat ops
```

`scripts/a2a/start-bus.sh` is a compatibility wrapper for the same bus commands.

## Throughput

Scale with **Cursor Cloud Extra High** (remote), not more local serve seats.
Directors coordinate via A2A and launch remote grunts. Kanban mirrors Extra High
cards; it is not a local worker spawner.
