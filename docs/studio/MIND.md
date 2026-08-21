# Seat mind (Grok Build harness)

This is the **Bot-equivalent mind** for Grok Cloud Studio Directors. ACP inject is leftover host OS: `session/prompt` into `grok agent serve` will never get in-process `deliver_wake()` (xAI does not take external PRs). Opted-in mind seats do **not** use `grok agent serve` or ACP `session/prompt`.

Python is **mailbox + pin + stay-up**. Grok is the agent for one turn.

## Law

Opt-in, floor + ops first. One long-lived process per seat.

```bash
export GCS_MIND_SEATS=floor,ops    # default empty; skipSeats stay skipped
scripts/a2a/start-studio-bus.sh start
# or: bash scripts/directors/seat-mind-loop.sh floor
```

`Donald` / `orchestrator` are Grok Bot seats, not mind seats. `skipSeats` is unchanged.

### State (disk only)

Under `$GCS_A2A_STATE/<seat>/mind/` (`GCS_A2A_STATE` defaults to `$GCS_ROOT/.a2a-state`):

| File | Role |
|---|---|
| `session` | Pinned grok session UUID (uuid4, created once) |
| `session.minted` | Written after the first grok exit 0 (later turns `--resume`) |
| `mail.txt` | Current inbox line for `--prompt-file` |
| `transcript.jsonl` | Grok json stdout plus the user mail row |
| `offset` | Byte offset into that seat’s `inbox.jsonl` (advanced only on grok exit 0) |
| `pid` | Live mind process |

Grok home: `$GCS_A2A_STATE/<seat>/grok-home` (`GROK_HOME`, `GROK_MEMORY=1`). Process cwd is `$GCS_ROOT`.

### Mail is a turn

Each inbox line (`scripts/directors/mind.py` `grok_cli_argv`):

```text
grok --resume "$PINNED_SESSION_UUID" --prompt-file "$mail" --verbatim \
    --output-format json --always-approve --permission-mode bypassPermissions \
    --max-turns 40
```

- Create the UUID once (`uuid4`), store in `mind/session`. First turn uses `--session-id $UUID` instead of `--resume`. Later turns **only** `--resume` that id.
- Never bare `-p`. Live proven 2026-08-21: `-p` before `--resume` is clap rc=2 because `--single` requires `<PROMPT>`. `--prompt-file` is the prompt and also triggers headless mode.
- `--agent-profile`, `--trust`, and `--plugin-dir` are **grok agent** flags, not grok headless. Do not put them on this argv.
- `--agent PATH` only if PATH is a file starting with YAML `---`. Markdown `SOUL.md` is not an agent file; omit `--agent`.
- If grok says the session is already in use, treat it as minted and `--resume` the same UUID. Do not mint a new UUID.
- Do not fork the session. Do not continue the latest-in-cwd session. Do not mint a new UUID because harvest was empty.
- `--max-turns 40` is grok’s own tool loop. Python does **not** parse grok stdout for function calls and does **not** run a second tool-calling loop.
- Persist grok json stdout onto `transcript.jsonl`. Bump `offset` only after grok exits 0.
- `MIND_FAIL` logs redacted stderr (240 chars). Never print secrets.

No ACP WebSocket. No `session/prompt`. No leftover pin-session / HANDOFF regex / 600s no-accept.

### Tools (which layer)

| Layer | What grok actually calls |
|---|---|
| Grok builtins | Shell, files, etc. inside grok |
| Seat `GROK_HOME/config.toml` | Taskboard stdio MCP: `taskboard --db $GCS_TASKBOARD_DB mcp` |
| `grok plugin install --trust` | `plugins/studio-mind` into seat `GROK_HOME` from `seat-mind-loop.sh` (`ticket`, `a2a_send`, `cloud_launch`) |

`--plugin-dir` cannot go on grok headless. `seat-mind-loop.sh` runs `grok plugin install "$ROOT/plugins/studio-mind" --trust` with that seat’s `GROK_HOME`. If install is skipped (no grok, missing dir, install fail), mind is MCP-only: taskboard is already in `config.toml`. Python `PLUGINS` in `scripts/directors/mind.py` remain as `call_plugin` helpers (tests, the studio-mind MCP server) — they are **not** a second agent loop.

A missing binary returns an error string from the MCP tool. Plugin output is redacted (`CURSOR_API_KEY`, webhook secrets, bearer tokens) and never printed as credentials.

## Bus

`start-studio-bus.sh` starts `seat-mind-loop.sh` for every seat in `GCS_MIND_SEATS` (even without `--daemons` — mind does not spawn `grok agent serve`).

- **Instead of ACP wake (default):** those seats skip `seat-wake-loop.sh` (`STUDIO_BUS_WAKE_SKIP reason=mind-owns-inbox`). Mind is the GROW path when opted in.
- **In addition:** set `GCS_MIND_PLUS_ACP_WAKE=1` to also start ACP wake for the same seats.
- **Do not kill existing serve.** Mind never calls `stop-seat-daemon.sh` / `ensure_seat_serve`. Leftover `grok agent serve` can keep running.

Leftover dispatch skips a live `mind/pid` (`DISPATCH_SKIP reason=mind-owns-inbox`) and does not steal `mind/offset`.

## Leftover ACP

`docs/A2A.md` GROW wake + `acp_inject.py --pin-session` remain for seats that still use serve. That path is leftover host OS, not this mind.

Board is **tcarac/taskboard**. Agent Kanban was removed; do not reconnect `ak`.
