# Studio crash-recovery checklist

1. **Reinstall / PATH** — `grok` (`~/.grok/bin`) and `ak` (`~/.local/bin` or `scripts/studio/agent-kanban/install-ak.sh`).
2. **Clear stale locks** — dead `daemon.pid` / `acp.inject.lock` under `.a2a-state/<seat>/`. `scripts/a2a/seat-lifecycle.sh status --all` clears stale pids.
3. **Inject lock TTL / timeout (already shipped)** — dispatch kills stale inject holders after lock TTL (`PALEMON_DISPATCH_LOCK_TTL_SEC` / `GCS_DISPATCH_LOCK_TTL_SEC`, default **240s**). ACP inject subprocess timeout defaults to **180s** (`PALEMON_ACP_INJECT_TIMEOUT` / `GCS_ACP_INJECT_TIMEOUT`). Crash recovery: stale lock files + TTL kill prevent wedged seats without restarting unrelated processes.
4. **No key on argv in logs** — `configure-ak.sh` / board-writer redacts api_key / bearer tokens from logged stderr; never commit connector-secrets or `.env` keys. Prefer connector JSON path over shell history.
5. **MemAvailable guard for board-writer** — `board-writer.sh` refuses start/once when `MemAvailable` < ~2GiB (`AK_WRITER_SKIP_LOW_MEM` / `AK_WRITER_MIN_AVAIL_KB`).
6. **Restart bus** — `scripts/a2a/start-studio-bus.sh start` (starts board-writer when configured; **never** `ak start`).
7. **Seats** — `scripts/a2a/seat-lifecycle.sh start --all` (A2A: `SEAT_UP` / `SEAT_DOWN`). Do **not** restart seats or kill `ama-runner` / board-writer unless a code change requires it.
8. **AK configure + writer ancestry** — `configure-ak.sh` then `board-writer.sh once|start` (`exec -a cursor-agent` + `CURSOR_AGENT=1` + leader login). Observer sync does not need the machine runner.
9. **Smoke** — `scripts/cloud/smoke-handoff.sh` (dry-run). Fleet bridge skips synthetic `bc-smoke-handoff-*` rows on the board.

## Agent Kanban observer notes

- Fleet cards = Extra High cloud agents mirrored by board-writer (not AK workers).
- Prefer observer-only; if AMA runner is left online it may claim Todo cards.
- Create tasks label-free; parse `ak` JSON through warning noise; recreate `dry-*` placeholders with `--force`.

Do not enable `ak start` as the studio worker daemon. Extra High remains the grunt path.
