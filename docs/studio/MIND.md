# Seat mind (Grok Build harness)

This is the **Bot-equivalent mind** for Grok Cloud Studio Directors. ACP inject is leftover host OS: `session/prompt` into `grok agent serve` will never get in-process `deliver_wake()` (xAI does not take external PRs).

Ultra-minimal Hermes / Grok-Bot / Pi / DeepSeek shape around **Grok Build**:

- Stateful Python core (`scripts/directors/mind.py`)
- Everything is a plugin (register in a dict: callable + JSON schema)
- Conversation state on disk, owned by the harness — not an ACP pin-session

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
| `transcript.jsonl` | Harness-owned conversation (user / assistant / tool rows) |
| `offset` | Byte offset into that seat’s `inbox.jsonl` |
| `pid` | Live mind process |

### Mail is a turn

`inbox.jsonl` growth → **one** model turn → persist transcript + offset.

- No ACP WebSocket
- No `session/prompt`
- No pin-session / HANDOFF regex / 600s no-accept
- No `grok --resume`

Turn completes when the **pluggable model runner** returns (scan-only or empty model text still counts). Fake runner in tests. Default runner:

```text
grok --permission-mode bypassPermissions --always-approve --trust \
     --cwd $GCS_ROOT -p "<composed prompt>" --output-format plain
```

`cwd=$GCS_ROOT`. `GROK_HOME=$GCS_A2A_STATE/<seat>/grok-home`. Never hardcode a box home or a product checkout path.

If the runner raises, the loop stays up and **does not** advance `offset`.

### Plugins

Registered in `PLUGINS` (`scripts/directors/mind.py`). Each is a Python callable plus a JSON schema. Ship three:

| Name | Action |
|---|---|
| `ticket` | `$TASKBOARD_BIN --db $GCS_TASKBOARD_DB ticket …` (default db `$GCS_A2A_STATE/taskboard/taskboard.db`) |
| `a2a_send` | `scripts/a2a/send.sh [--from SEAT] <seat> <text>` |
| `cloud_launch` | `scripts/launch-cloud-extra-high.sh [--name NAME] PROMPT` |

A missing binary returns an error string. The loop does not crash. Plugin output is redacted (`CURSOR_API_KEY`, webhook secrets, bearer tokens) and never printed as credentials.

The model emits tool calls as JSON (`{"name": "ticket", "arguments": {"argv": ["list"]}}`) or as structured `tool_calls` from a fake runner. Tools run after the runner returns; that is still one mail turn.

## Bus

`start-studio-bus.sh` starts `seat-mind-loop.sh` for every seat in `GCS_MIND_SEATS` (even without `--daemons` — mind does not spawn `grok agent serve`).

- **Instead of ACP wake (default):** those seats skip `seat-wake-loop.sh` (`STUDIO_BUS_WAKE_SKIP reason=mind-owns-inbox`). Mind is the GROW path when opted in.
- **In addition:** set `GCS_MIND_PLUS_ACP_WAKE=1` to also start ACP wake for the same seats.
- **Do not kill existing serve.** Mind never calls `stop-seat-daemon.sh` / `ensure_seat_serve`. Leftover `grok agent serve` can keep running.

Leftover dispatch skips a live `mind/pid` (`DISPATCH_SKIP reason=mind-owns-inbox`) and does not steal `mind/offset`.

## Leftover ACP

`docs/A2A.md` GROW wake + `acp_inject.py --pin-session` remain for seats that still use serve. That path is leftover host OS, not this mind.

Board is **tcarac/taskboard**. Agent Kanban was removed; do not reconnect `ak`.
