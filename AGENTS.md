# Grok Cloud Studio

Public control plane for Grok Build CLI Directors and Cursor Cloud Extra High grunts.

- Extra High target repo: set `GCS_CLOUD_REPO` or `CLOUD_REPO_URL` (required).
- Bind Grok Bot orchestrator: set `GCS_BOT_AGENT_ID` then `./install.sh` or `scripts/a2a/bind-bot-agent.sh`. Bot seats are not ACP inject targets.
- Never print or commit credentials (`CURSOR_API_KEY`, webhook secrets, ACP tokens).
- ACP daemons are opt-in: `scripts/a2a/start-studio-bus.sh start --daemons`. That starts one `grok agent serve` per GROW seat plus `seat-wake-loop.sh` / `wake-daemon.py` (inbox → `session/prompt` inside that serve pid; never `grok --resume`) and `host-ticker.py` keep-alives.
- Opt-in Grok Build mind (Bot-equivalent; default off): `GCS_MIND_SEATS=floor,ops` then `start-studio-bus.sh start` runs `seat-mind-loop.sh` / `mind.py` (mailbox + pin + stay-up; inbox → `grok --resume` pinned UUID `--prompt-file`, never bare `-p`; grok `--model grok-4.6 --reasoning-effort xhigh`; `grok plugin install --trust` of `plugins/studio-mind` into seat GROK_HOME; no ACP inject). Default `GCS_MIND_RUNNER=auto` persists `$GCS_A2A_STATE/<seat>/mind/runner` (`grok`|`cursor`); each mail line uses that file. On quota / HTTP 402, flip and retry that same mail line once on the other runner (`MIND_SWITCH`); forced `GCS_MIND_RUNNER=grok|cursor` does not flip. Cursor CLI is `cursor-grok` or `agent --model cursor-grok-4.6-xhigh` with a separate `mind/cursor-session` pin; do not remint the grok UUID. Mind is the GROW path when opted in; ACP inject is leftover host OS. See `docs/studio/MIND.md`. Do not kill existing serve.
- Pin `acp.session`. HANDOFF only on this-prompt STATUS (`reason=status`) or a this-prompt work tool on invoked argv (`reason=work`). Stay connected through keep-alive chatter, inspect tools, payload blobs, silence, leftover tools, RESULT-only, and `queue/changed`. Dead session: one `session/new` after 3 no-start nacks (`ACP_INJECT_SESSION_DEAD`; nack 120s). RESULT is duplex, not success. Directors print `RESULT bc-id=<id or none> pr=<url or none> a2a=<task-id or none> notes=<one line>`. RESULT-only / PONG is a bug. Do not `session/cancel` a handed-off live turn.
- After `CLOUD_LAUNCH_OK`, do not block on watch; the waiter A2A-pings the owning seat.
- MCP = tools (`plugins/a2a`, `plugins/cursor-cloud`). Seat taskboard stdio MCP lives in each isolated `GROK_HOME/config.toml` (`taskboard --db $GCS_TASKBOARD_DB mcp`), never Cursor `${workspaceFolder}`. A2A = seat-to-seat.
- Board is tcarac/taskboard (ticket CLI + HTTP `/mcp`). Agent Kanban was removed.
- Palemon studio wipe: `docs/studio/WIPE.md` (`studio.env.example` → `$GCS_A2A_STATE/studio.env`; board scripts under `scripts/studio/taskboard/`; `start-studio-bus.sh start` with **no** `--daemons`).
- Director prompts: `prompts/` or `docs/studio/directors/*_director_prompt.txt` (`GCS_PROMPT_DIR`). Remint must resolve either layout.
- Ship gate: `.venv/bin/pytest -q` and `python3 scripts/secret_scan.py`.
