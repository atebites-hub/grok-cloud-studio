# Grok Cloud Studio

Public control plane for Grok Build CLI Directors and Cursor Cloud Extra High grunts.

- Extra High target repo: set `GCS_CLOUD_REPO` or `CLOUD_REPO_URL` (required).
- Bind Grok Bot orchestrator: set `GCS_BOT_AGENT_ID` then `./install.sh` or `scripts/a2a/bind-bot-agent.sh`. Bot seats are not ACP inject targets.
- Never print or commit credentials (`CURSOR_API_KEY`, webhook secrets, ACP tokens).
- ACP daemons are opt-in: `scripts/a2a/start-studio-bus.sh start --daemons`. That starts one `grok agent serve` per GROW seat plus `seat-wake-loop.sh` / `wake-daemon.py` (inbox → `session/prompt` inside that serve pid; never `grok --resume`) and `host-ticker.py` keep-alives.
- Pin `acp.session`. HANDOFF only on this-prompt STATUS (`reason=status`) or a this-prompt work tool on invoked argv (`reason=work`). Stay connected through keep-alive chatter, inspect tools, payload blobs, silence, leftover tools, RESULT-only, and `queue/changed`. Dead session: one `session/new` after 3 no-start nacks (`ACP_INJECT_SESSION_DEAD`; nack 120s). RESULT is duplex, not success. Do not `session/cancel` a handed-off live turn.
- After `CLOUD_LAUNCH_OK`, do not block on watch; the waiter A2A-pings the owning seat.
- MCP = tools (`plugins/a2a`, `plugins/cursor-cloud`). A2A = seat-to-seat.
- Board is tcarac/taskboard (ticket CLI + HTTP `/mcp`). Agent Kanban was removed.
- Ship gate: `.venv/bin/pytest -q` and `python3 scripts/secret_scan.py`.
