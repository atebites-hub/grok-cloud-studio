# Grok Cloud Studio

Public control plane for Grok Build CLI Directors and Cursor Cloud Extra High grunts.

- Extra High target repo: set `GCS_CLOUD_REPO` or `CLOUD_REPO_URL` (required).
- Bind Grok Bot orchestrator: set `GCS_BOT_AGENT_ID` then `./install.sh` or `scripts/a2a/bind-bot-agent.sh`. Bot seats are not ACP inject targets.
- Never print or commit credentials (`CURSOR_API_KEY`, webhook secrets, ACP tokens).
- ACP daemons are opt-in: `scripts/a2a/start-studio-bus.sh start --daemons`.
- After `CLOUD_LAUNCH_OK`, do not block on watch; the waiter A2A-pings the owning seat.
- MCP = tools (`plugins/a2a`, `plugins/cursor-cloud`). A2A = seat-to-seat.
- Ship gate: `.venv/bin/pytest -q` and `python3 scripts/secret_scan.py`.
