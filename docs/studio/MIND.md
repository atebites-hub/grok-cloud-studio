# Seat mind (Grok Build harness)

This is the **Bot-equivalent mind** for Grok Cloud Studio Directors. ACP inject is leftover host OS: `session/prompt` into `grok agent serve` will never get in-process `deliver_wake()` (xAI does not take external PRs). Opted-in mind seats do **not** use `grok agent serve` or ACP `session/prompt`.

Python is **mailbox + pin + stay-up**. Default `GCS_MIND_RUNNER=auto` persists
`$GCS_A2A_STATE/<seat>/mind/runner` (`grok` or `cursor`). Each mail line uses
that file. On HTTP 402 / `usage balance exhausted`, flip the file and retry
**that same mail line** once on the other runner (`MIND_SWITCH`). Forced
`GCS_MIND_RUNNER=grok` or `cursor` does not flip. Cursor CLI uses a **separate**
chat pin. The switch is still one turn, not a second Python tool loop.

## Law

Opt-in, floor + ops first. One long-lived process per seat.

```bash
export GCS_MIND_SEATS=floor,ops    # default empty; skipSeats stay skipped
scripts/a2a/start-studio-bus.sh start
# or: bash scripts/directors/seat-mind-loop.sh floor
```

`Donald` / `orchestrator` are Grok Bot seats, not mind seats. `skipSeats` is unchanged.

### Two-runtime mind law

Mind is mind/IaC, not another ACP wrapper. One mailbox: `inbox.jsonl` + `mind/offset` + pin (`mind/session` grok UUID, `mind/cursor-session` Cursor chat id). Grok runner and Cursor CLI runner **share** that mailbox. Offset advances only on runner exit 0.

**Do not copy GROK_HOME MCP into Cursor CLI.** Two catalogs. Never fake a transfer.

- Grok catalog: seat `GROK_HOME/config.toml` (taskboard stdio `taskboard --db $GCS_TASKBOARD_DB mcp` plus Linear HTTP `https://mcp.linear.app/mcp`). Grok minds get Linear via this GROK_HOME catalog, not via Cursor `.cursor/mcp.json`. Studio Linear is **Living Sky** (`linear.app/livingsky`, team Livingsky / `LIV`). **NEVER Black Swan Money.** `${LINEAR_API_KEY}` expands at grok load time (never print, never commit). Linear tools: `save_issue`, `save_comment`, `prepare_attachment_upload`. Plus `grok plugin install --trust` of `plugins/studio-mind`. Grok-home Higgsfield is grok-only, for when grok usage is back. Do not put Higgsfield keys on MCP argv.
- Cursor CLI catalog: repo `.cursor/mcp.json` wrapping `scripts/studio/taskboard/run-mcp.sh` (same `taskboard --db $DB mcp`, no `GROK_HOME`) **and** Linear HTTP at `https://mcp.linear.app/mcp` with `Authorization: Bearer ${LINEAR_API_KEY}`. Linear + taskboard only — do not copy the Grok MCP catalog into Cursor. Higgsfield is Cursor catalog login when the runner is Cursor CLI (Art generate). Grok Bot Higgsfield is a different catalog. `doctor.sh` / `recover.sh` fail-closed if art MCP would leak keys.

Cursor Cloud Extra High agents cannot scrape `GROK_HOME`. Give them Linear via cloud-env: snapshot / dashboard Secrets / process env `LINEAR_API_KEY`, plus checkout `.cursor/mcp.json` (Linear + taskboard). RUNNING specialists `save_comment` on Living Sky (`LIV`). They never inherit seat GROK_HOME `config.toml`.

Shared tools on PATH only: `ticket` / `tb`, `scripts/a2a/send.sh`, `scripts/launch-cloud-extra-high.sh`.

No third Python tool loop. No ACP `session/prompt` GROW. No `deliver_wake` overlay.

The grunt is **Cursor Cloud** (not "Extra High" as the noun, not "Cursor Cloud API"). Effort **grok-4.6 xhigh**, `fast=false`. Grok mind CLI: `--model grok-4.6 --reasoning-effort xhigh` (extra-high). Cursor fallback: `--model cursor-grok-4.6-xhigh` only. The PATH launcher stays `scripts/launch-cloud-extra-high.sh`.

### State (disk only)

Under `$GCS_A2A_STATE/<seat>/mind/` (`GCS_A2A_STATE` defaults to `$GCS_ROOT/.a2a-state`):

| File | Role |
|---|---|
| `session` | Pinned grok session UUID (uuid4, created once) |
| `session.minted` | Written after the first grok exit 0 (later grok turns `--resume`) |
| `cursor-session` | Pinned Cursor chat id (from `agent create-chat`; not the grok UUID) |
| `mail.txt` | Current inbox line (grok `--prompt-file`; Cursor positional prompt) |
| `turn.txt` | Latest harvested mail turn (Bot `bot-wake.txt` analog). Written **before** the runner. |
| `turn.jsonl` | Append log of harvested turns (Bot `bot-wake.jsonl` analog) |
| `transcript.jsonl` | Agent json stdout plus the user mail row |
| `offset` | Byte offset into that seat’s `inbox.jsonl` (advanced only on runner exit 0) |
| `pid` | Live mind process |
| `runner` | Persisted `grok` or `cursor` for `GCS_MIND_RUNNER=auto`. Missing file means grok. Forced env does not rewrite this file. |

Grok home: `$GCS_A2A_STATE/<seat>/grok-home` (`GROK_HOME`, `GROK_MEMORY=1`). Process cwd is `$GCS_ROOT`. Cursor runner does **not** set `GROK_HOME`.

### Mail is a turn (grok)

Executable BDD example (Living Sky **LIV-63** remaining, grok-bot-like):
[`tests/features/liv63_mind_bot_like.feature`](../../tests/features/liv63_mind_bot_like.feature).
Mailbox harvest writes `mind/mail.txt` + `mind/turn.txt` before the runner
(Bot-like wake analog). Spawn PATH remaining is `cloud_launch` →
`scripts/launch-cloud-extra-high.sh` plus `a2a_send` → `scripts/a2a/send.sh`.
Do not vendor Hermes. Do not land harvest mailbox PRs #26 and #28.

Each inbox line (`scripts/directors/mind.py` `grok_cli_argv`). Live clap (2026-08-21, #21):

```text
# first grok turn (UUID already in mind/session; Cursor has no equivalent flag)
grok --session-id "$PINNED_SESSION_UUID" --prompt-file "$mail" --verbatim \
    --output-format json --always-approve --permission-mode bypassPermissions \
    --max-turns 40 --model grok-4.6 --reasoning-effort xhigh

# later grok turns
grok --resume "$PINNED_SESSION_UUID" --prompt-file "$mail" --verbatim \
    --output-format json --always-approve --permission-mode bypassPermissions \
    --max-turns 40 --model grok-4.6 --reasoning-effort xhigh
```

- Create the UUID once (`uuid4`), store in `mind/session`. First turn uses `--session-id $UUID` instead of `--resume`. Later turns **only** `--resume` that id.
- Never bare `-p` on grok. Live proven 2026-08-21: `-p` before `--resume` is clap rc=2 because `--single` requires `<PROMPT>`. `--prompt-file` is the prompt and also triggers headless mode.
- Spawn identity (remaining vs construction clap): `grok_cli_runner` asserts `--prompt-file` is `$GCS_A2A_STATE/<seat>/mind/mail.txt` and `--resume` / `--session-id` equals `mind/session`. Refuse `--continue`, `--fork-session`, `--print`, glued `--resume=-1`, and a positional prompt. Executable BDD: [`tests/features/liv62_pinned_mail_spawn.feature`](../../tests/features/liv62_pinned_mail_spawn.feature).
- `--agent-profile`, `--trust`, and `--plugin-dir` are **grok agent** flags, not grok headless. Do not put them on this argv.
- `--agent PATH` only if PATH is a file starting with YAML `---`. Markdown `SOUL.md` is not an agent file; omit `--agent`.
- If grok says the session is already in use, treat it as minted and `--resume` the same UUID. Do not mint a new UUID.
- Do not fork the session. Do not continue the latest-in-cwd session. Do not mint a new UUID because harvest was empty. Do not remint because the runner switched.
- `--max-turns 40` is grok’s own tool loop. Python does **not** parse grok stdout for function calls and does **not** run a second tool-calling loop.
- Offset advances only after the effective runner exits 0. That same success marks the hub task `TASK_STATE_COMPLETED`. `send.sh` / hub enqueue is `TASK_STATE_SUBMITTED`. Hub `TASK_STATE_COMPLETED` / A2A ACK is a **receipt, not mind-turn done**. Do not treat send.sh `kind=receipt` as `MIND_TURN`. Mail is consumed only after grok/cursor runner exit 0. A runner that did not run is not success. A failed runner leaves mail queued (offset unchanged, task not completed).
- `MIND_FAIL` logs redacted stderr (240 chars). Never print secrets.

### RESULT is duplex, not success

Mailbox consume is runner exit 0, not a RESULT line. After a successful turn,
`duplex_after_mind` writes a Director RESULT onto the A2A task (`scripts/a2a/duplex.py`)
and may ping the caller (`A2A_REPLY`). That ping must succeed: skipSeat `donald` has
no shipped Agent Card, so duplex maps `donald` → `floor-ops` then `orchestrator`
instead of POSTing a hub 404. A missed ping does not fail the task reply.
Hub enqueue is `TASK_STATE_SUBMITTED`; later `TASK_STATE_COMPLETED` / send.sh ACK is a
protocol receipt, not mind-turn done (not this mechanic).

Directors print:

```text
RESULT bc-id=<id or none> pr=<url or none> a2a=<task-id or none> notes=<one line>
```

`wrap_mind_mail` prepends that law plus `A2A_TASK_ID` / `A2A_CONTEXT`. RESULT-only /
PONG is a bug. PONG is not a RESULT line. A2A_REPLY is a duplex caller ping — never
launch a Cursor Cloud agent or Bot CloudAgent for it. Extra High stays **grok-4.6
xhigh**, `fast=false`.

No ACP WebSocket. No `session/prompt`. No leftover pin-session / HANDOFF regex / 600s no-accept.

### Mind runner SWITCH (`GCS_MIND_RUNNER=auto`)

Default **`GCS_MIND_RUNNER=auto`**. Persist `$GCS_A2A_STATE/<seat>/mind/runner`
(`grok` or `cursor`). Each mail line uses the persisted runner. Do **not**
probe grok every line after a 402.

On quota / HTTP 402 / `usage balance exhausted`, flip the file and retry
**that same mail line once** on the other runner. Offset advances only on
exit 0. Log:

```text
MIND_SWITCH seat=floor from=grok to=cursor reason=quota-exhausted
```

Forced `GCS_MIND_RUNNER=grok` or `GCS_MIND_RUNNER=cursor` does **not** flip
(and does not rewrite `mind/runner`). Missing `mind/runner` under auto starts
as grok; a successful auto turn writes the runner that won.

Do not consume/advance `offset` unless the effective runner exits 0. Hub
COMPLETE / A2A ACK is a receipt, not that success. If the
retry also fails, keep today’s `MIND_FAIL` / 2s runner-fail sleep (do not
tight-loop faster). Do not fork sessions. Do not become a 45s assigner. Do
not set `GROK_BIN=cursor-grok`. Do not reuse `mind/session` (that UUID is
grok-only). Do not remint the grok UUID because the runner switched.

Binary: existing `cursor-grok` wrapper if present on PATH, else `agent`.
Override with `GCS_CURSOR_BIN` (tests/ops). Grok runner model is **`grok-4.6`** with **`--reasoning-effort xhigh`** (extra-high). Cursor model is **`cursor-grok-4.6-xhigh` only**. Never another Cursor model.

Auth: `CURSOR_API_KEY` already in the environment, or sourced from `~/.config/cursor/agent.env` (`CURSOR_AGENT_ENV` override). Never print the key. Never put it on argv.

Mint a Cursor chat with `agent create-chat` (Cursor has no `--session-id`). Pin the id in `mind/cursor-session`. Later turns **only** `--resume` that id. Never resume the grok UUID. Never `--continue` (alias for resume `-1`). Never resume `-1`. Never latest-in-cwd.

Cursor has no `--prompt-file`. Pass the mail text as the positional prompt (mind already writes `mail.txt`). cwd remains `$GCS_ROOT`.

```text
# mint once
agent create-chat

# every Cursor turn (including the first prompt after mint)
agent --resume "$CURSOR_CHAT_ID" -p --force --output-format json --trust \
    --approve-mcps --model cursor-grok-4.6-xhigh "$PROMPT"
```

`-p` / `--print`, `--force` (or `--yolo`), `--output-format json`, `--trust`, and `--approve-mcps` are the Cursor headless clap. `--trust` here is a Cursor headless flag, not grok’s `--trust` on `plugin install`.

### Tools (which layer)

| Layer | What grok actually calls |
|---|---|
| Grok builtins | Shell, files, etc. inside grok |
| Seat `GROK_HOME/config.toml` | Taskboard stdio MCP: `taskboard --db $GCS_TASKBOARD_DB mcp`. Linear HTTP catalog: `url = "https://mcp.linear.app/mcp"` (`save_issue`, `save_comment`). Living Sky / `LIV`. Never Black Swan Money. |
| `grok plugin install --trust` | `plugins/studio-mind` into seat `GROK_HOME` from `seat-mind-loop.sh` (`ticket`, `a2a_send`, `cloud_launch`) |

`--plugin-dir` cannot go on grok headless. `seat-mind-loop.sh` runs `grok plugin install "$ROOT/plugins/studio-mind" --trust` with that seat’s `GROK_HOME`. Already-installed / idempotent reinstall is `MIND_PLUGIN_OK` (grok may print `Error: repo studio-mind-... already installed` and exit non-zero). If install is skipped (no grok, missing dir, genuine install fail), mind is MCP-only: taskboard is already in `config.toml`. Python `PLUGINS` in `scripts/directors/mind.py` remain as `call_plugin` helpers (tests, the studio-mind MCP server) — they are **not** a second agent loop. Do not copy `GROK_HOME` MCP into Cursor CLI.

Cursor runner: GROK_HOME taskboard MCP, Linear GROK_HOME HTTP, and grok `--plugin-dir` **do not transfer**. Two catalogs (see Two-runtime mind law). Cursor CLI uses Cursor builtins plus repo `.cursor/mcp.json` (Linear + taskboard only), never a copied `GROK_HOME`. Shared tools on PATH only: `ticket` / `tb`, `scripts/a2a/send.sh`, `scripts/launch-cloud-extra-high.sh`. No third Python tool loop.

A missing binary returns an error string from the MCP tool. Plugin output is redacted (`CURSOR_API_KEY`, webhook secrets, bearer tokens) and never printed as credentials.

## Bus

`start-studio-bus.sh` starts `seat-mind-loop.sh` for every seat in `GCS_MIND_SEATS` (even without `--daemons` — mind does not spawn `grok agent serve`).

- **Instead of ACP wake (default):** those seats skip `seat-wake-loop.sh` (`STUDIO_BUS_WAKE_SKIP reason=mind-owns-inbox`). Mind is the GROW path when opted in.
- **In addition:** set `GCS_MIND_PLUS_ACP_WAKE=1` to also start ACP wake for the same seats.
- **Do not kill existing serve.** Mind never calls `stop-seat-daemon.sh` / `ensure_seat_serve`. Leftover `grok agent serve` can keep running.

Leftover dispatch skips a live `mind/pid` and current `GCS_MIND_SEATS` (`DISPATCH_SKIP reason=mind-owns-inbox`) and does not steal `mind/offset`. It re-reads `mind_seats()` on each poll (does not freeze the set at import), so a long-lived process still skips a newly staffed mind seat even before a bounce.

`start-studio-bus.sh start` recycles leftover dispatch **only** when `.a2a-state/dispatch.mind-seats` differs from the current env / `studio.env` set (missing file is the empty set). Matching keeps `STUDIO_BUS_DISPATCH_ALREADY`. Recycle does not kill hub, fleet-shepherd, seat minds, host ticker, or `grok agent serve`. Default-off `start` / `recover.sh` evict leftover live `bot-bridge.pid` (`ALREADY` only when `GCS_BOT_BRIDGE=1`; do not remint). `start` / `recover.sh` do not start bot-bridge unless `GCS_BOT_BRIDGE=1`.

## Leftover ACP

`docs/A2A.md` GROW wake + `acp_inject.py --pin-session` remain for seats that still use serve. That path is leftover host OS, not this mind.

Board is **tcarac/taskboard**. Agent Kanban was removed; do not reconnect `ak`.

## CCGS leads

Mind seats for CCGS leads (not a 49-specialist floor). Directors and leads spawn
specialists only via `scripts/launch-cloud-extra-high.sh`.

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
| audio | `audio` (first-class) |
| narrative | `narrative` (first-class) |

Unmapped specialist titles do not mint mind or GROW seats (`lib.py known`
fails closed). Aliases live in `scripts/a2a/lib.py` `CCGS_LEAD_ALIASES`.
FAT: [`tests/features/ccgs_audio_narrative_map.feature`](../../tests/features/ccgs_audio_narrative_map.feature).

