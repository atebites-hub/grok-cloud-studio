# Studio crash-recovery checklist

1. **Reinstall / PATH** — `grok` (`~/.grok/bin`) and `ak` (`~/.local/bin` or `scripts/studio/agent-kanban/install-ak.sh`).
2. **Clear stale locks** — dead `daemon.pid` / `acp.inject.lock` under `.a2a-state/<seat>/`. `scripts/a2a/seat-lifecycle.sh status --all` clears stale pids.
3. **Restart bus** — `scripts/a2a/start-studio-bus.sh start`.
4. **Seats** — `scripts/a2a/seat-lifecycle.sh start --all` (A2A: `SEAT_UP` / `SEAT_DOWN`).
5. **AK configure** — `configure-ak.sh` then `bootstrap-board.sh`.
6. **Smoke** — `scripts/cloud/smoke-handoff.sh` (dry-run).

Do not enable `ak start` as the studio worker daemon. Extra High remains the grunt path.
