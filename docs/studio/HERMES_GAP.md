# Hermes v0.21 vs Grok Cloud Studio hive

Living Sky **LIV-62**. Compared on 2026-09-01 against:

- Hermes Agent **v0.21.0** (Pantheon), tag
  [`v2026.8.31`](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.31)
  and public docs at [hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs/).
- Grok Cloud Studio **this repo** (control plane after PR #25: extra-high grok
  mind, CCGS leads, taskboard v0.6.0). Hive narrative:
  [`docs/studio/HIVE.md`](HIVE.md).

This is a **gap analysis**. It is **not a copy of Hermes**. Do **not vendor**
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).
Do not add a `vendor/hermes-agent` submodule. Do not import `plugin.yaml`
SDK, Bot Mode roster, `message_agent`, or the 49-specialist floor.

Strategy: selective **borrow** of mailbox ideas into the existing grok
mailbox. Not feature parity. Not an agent OS inside GCS.

## How to read the matrix

| Tag | Meaning |
|---|---|
| **Already** | GCS has an equivalent with different machinery. Do not replace it with Hermes. |
| **Borrow** | Idea is useful. Re-implement on the grok mailbox / Extra High path. Never copy source. |
| **Skip** | Intentional ≠. Hermes product surface that would make GCS a Hermes clone or a 15GB OOM. |

Severity for residual **Borrow** rows: S1 = mailbox honesty, S2 = Director
command surface, S3 = nice-to-have / already covered by another PR.

## Matrix

| Hermes v0.21 surface | GCS hive today | Tag | Notes |
|---|---|---|---|
| Named persistent agents (Bot Mode roster, faces, group chats) | First-class seats + `SOUL.md` / `MEMORY.md` | **Already** / **Skip** roster UX | Seats are Directors, not a chat-app society. No avatars, no Discord-style rooms, no `@-mention` composer. |
| `hermes peer` bot-to-bot DMs | `scripts/a2a/send.sh` → hub `inbox.jsonl` | **Already** | A2A is HTTP+JSON on `127.0.0.1:8732`. Durable JSONL, not Bot Chat cards. |
| Mail is a turn (Agent Inbox → one CLI turn) | `mind.py`: one inbox line → one `grok --prompt-file` / Cursor positional prompt | **Already** | Grok `--max-turns 40` is grok's loop. Python does not tool-call. |
| Server-side sender envelope + inbound defang + body cap | Raw JSONL line into `mail.txt` | **Borrow** S1 | Harvest PRs #26/#28. Do not vendor Hermes filter code. |
| Stay-up daemon + heartbeat | `seat-mind-loop.sh` / `mind.py` loop; leftover `grok agent serve` | **Already** / **Borrow** heartbeat | Empty harvest must not remint. `mind/heartbeat` is optional liveness (#26). |
| Hub task state vs harvest | `message:send` returns `TASK_STATE_COMPLETED` (receipt) | **Borrow** S1 **no fake COMPLETE** | Footer already says receipt ≠ acted. Honest A2A: enqueue `SUBMITTED`; `COMPLETED` only after harvest **and** runner exit 0 (#27/#28). |
| `delegate_task` + live mid-flight steer, 10 concurrent children | Extra High via `scripts/launch-cloud-extra-high.sh`; followup scripts; waiter A2A ping | **Already** / **Skip** steer-API | Grunts are remote Cursor Cloud, not in-process Hermes children. Follow-up exists; do not copy `delegate_task`. |
| Cron jobs with memory + continuity + monitor-mode | `host-ticker.py` `ACP_PING STATUS/CONTINUE` (default 600s) | **Skip** as assigner / **Already** as stay-up | Ticker is keep-alive work turns, **not** a 45s central assigner, **not** LAUNCH, **not** Hermes cron. Do not build unattended job fleets on the studio box. |
| MCP command center (desktop catalog, health, cost overlay, `hermes://` install) | Two catalogs: seat `GROK_HOME/config.toml` + repo `.cursor/mcp.json`; `plugins/studio-mind` (`ticket`, `a2a_send`, `cloud_launch`) | **Already** split / **Borrow** S2 list/status | Do not copy GROK_HOME into Cursor CLI. Optional PATH/MCP: `a2a_list_seats`, `cloud_status`, `cloud_result`, `cloud_list`, `cloud_followup` (#26/#30). No desktop MCP page. |
| Skills Hub + autonomous skill creation | Director prompts + `common_footer.txt` + grok plugins | **Skip** | GCS is not a skill marketplace. Prompts live in `prompts/` or `docs/studio/directors/`. |
| MEMORY.md / USER.md + Honcho dialectic + FTS5 session search | Per-seat `docs/studio/directors/souls/<seat>/{SOUL.md,MEMORY.md}` + `GROK_MEMORY=1` | **Already** (disk souls) / **Skip** providers | Bounded Hermes memory tools and Honcho stay out. Do not share one GROK_HOME across seats. |
| Messaging gateway (Telegram, Discord, Slack, WhatsApp, Signal) + relay live-cards | Local A2A + optional Grok Bot wake (`bot-bridge`) | **Skip** | Studio box is not a consumer messenger. Bot seats stay `skipSeats`. |
| In-app browser the agent drives | Extra High / grok builtins / optional chrome-devtools on grok catalog | **Skip** as Hermes desktop browser | Playtest browser is a specialist tool, not a bundled OS tab. |
| Kanban desktop plugin | tcarac/taskboard v0.6.0 (`vendor/taskboard` submodule only) | **Skip** | Agent Kanban was removed. Do not reconnect `ak`. Do not vendor Hermes Kanban. |
| Plugin SDK (`plugin.yaml`), Bot Mode plugin, 40+ core tools | Thin PATH wrappers + MCP planes (`plugins/a2a`, `plugins/cursor-cloud`, `plugins/studio-mind`) | **Skip** SDK / **Already** thin tools | Do not vendor the Hermes plugin tree. |
| Protected writes to AGENTS.md / skills / memory | Mind argv is `--always-approve` / `bypassPermissions` (grok) and `--force` (Cursor) | **Skip** for now | Intentional: Directors are trusted on the studio box. Extra High has its own approval model. Do not import Hermes approval UX. |
| Oversized tool-result spill, compression, MoA, provider catalog | Owned by grok / Cursor runtimes | **Skip** | GCS does not reimplement the agent loop. |
| Session pin / resume | `mind/session`, `mind/cursor-session`, leftover `acp.session` | **Already** | Pin forever. One `session/new` only after 3 no-start nacks on leftover ACP. |
| Subagent worktrees / git isolation | Extra High PR branches | **Already** | Isolation is remote git, not local Hermes worktrees. |
| Verify subsystem / completion = evidence | Waiter `FLEET_DONE`; RESULT is duplex not success | **Already** | Do not treat hub ACK or RESULT-only as done. |
| Terminal TUI, command palette, terminal pets | Out of scope | **Skip** | GCS is scripts + seats, not a TUI product. |
| Seven terminal backends (Docker, SSH, Modal, Daytona, …) | Studio box + Cursor Cloud VMs | **Skip** | Extra High is the sandbox. |
| 49-specialist Bot Mode roster | CCGS leads only; specialists are Extra High | **Skip** | Hard law. Tests in `tests/test_ccgs_leads.py`. |

## Already (do not replace)

GCS already has a hive. It is smaller and stricter than Hermes:

1. **Named Directors** with souls, isolated `GROK_HOME`, pinned sessions.
2. **Seat-to-seat mail** that the mind harvests as one turn.
3. **Remote grunt spawn** with waiter → owning seat (not in-process children).
4. **A board** (taskboard), not a worker spawner.
5. **Two-runtime mind law** (grok extra-high / Cursor `cursor-grok-4.6-xhigh`) with quota SWITCH.
6. **Completion honesty at the Director layer**: RESULT and hub ACK are not success.

Replacing those with Hermes Bot Mode would throw away the Extra High split
and OOM the box.

## Borrow (ideas only, no vendor)

Re-implement on GCS machinery if the floor wants them. Existing harvest PRs
are optional code; this ticket is the analysis.

| Idea | GCS place | Why |
|---|---|---|
| Mail envelope + defang + 16k cap | `mind.py` before `--prompt-file` | Stop prompt-injection via A2A body; cap giant mail. |
| **No fake COMPLETE** | `hub.py` enqueue `SUBMITTED`; mind marks `COMPLETED` on runner exit 0 | Hub ACK today is too loud. Footer already warns. |
| Stay-up heartbeat file | `mind/heartbeat` on every `process_once` | Empty harvest must still prove the loop is alive. |
| Command-center **scripts**, not a desktop | studio-mind + PATH: list seats, cloud status/list/followup/result | Directors should not shell-hunt. Still Extra High only for spawn. |

Do **not** borrow: Bot Mode, group chats, cron-as-funnel, Kanban plugin,
skills hub, Honcho, messaging gateways, in-app browser, plugin SDK,
`message_agent`, mid-flight Hermes child steer.

## Skip (intentional ≠)

These Hermes surfaces stay out of GCS on purpose:

- Vendoring or submodule of `hermes-agent`.
- 49 local specialist seats / Bot Mode society UX.
- Hermes Kanban (board stays tcarac/taskboard).
- Copying `GROK_HOME` MCP into Cursor CLI.
- Grok Bot as the Extra High grunt runtime.
- ACP `session/prompt` as the opted-in mind path.
- A 45s central assigner (ticker is STATUS/CONTINUE, not LAUNCH).
- Consumer messengers and relay live-cards on the studio box.
- Hermes desktop browser as the playtest path.

## Related PRs (code, not this doc)

| PR | Role vs LIV-62 |
|---|---|
| #26 mind-hive harvest | Ports mailbox envelope/defang/heartbeat/list tools. **Not** a vendor. Overlaps Borrow S1/S2. |
| #28 rebase of #26 + no fake COMPLETE | Same, plus hub `SUBMITTED`. |
| #27 queue mail / bot-bridge default off | Adjacent mailbox honesty. |
| #30 Extra High control plane | Spawn/list/followup for Directors. Not Hermes. |
| #38 / #40 Linear MCP | Living Sky tools on both runtimes. Not a Hermes copy. |

LIV-62 ships the **document**. Do not merge Hermes source to close this
ticket.

## Follow-ups (GCS tickets, not Hermes ports)

1. Decide whether Borrow S1 (envelope, defang, no fake COMPLETE) lands via
   #26/#28 or a slimmer mailbox PR.
2. Keep Linear MCP (#38/#40) as the Living Sky surface; this hive doc is what
   those seats should read.
3. Do not open a "port Hermes Kanban" or "port Bot Mode" ticket.

## Sources (no vendored tree)

- Hermes v0.21.0 release notes (Pantheon): Bot Mode, `hermes peer`, cron
  continuity, live `delegate_task`, MCP command center, in-app browser,
  Kanban hardening, skills wave, memory files.
- Hermes docs: [memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory),
  [cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron),
  [MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp).
- GCS: `docs/ARCHITECTURE.md`, `docs/A2A.md`, `docs/studio/MIND.md`,
  `docs/studio/TASKBOARD.md`, `docs/studio/GROK_LEADER.md`,
  `docs/studio/WIPE.md`, `scripts/directors/mind.py`, `scripts/a2a/hub.py`.
