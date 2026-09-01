# Grok Cloud Studio

Living Sky Linear **LIV-62**. Paste this page into a Linear Document.
This is the hive. It is **not a copy of Hermes**. Do **not vendor**
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

Compared against Hermes Agent **v0.21.0** (tag `v2026.8.31`, Pantheon).
Full matrix: [`docs/studio/HERMES_GAP.md`](HERMES_GAP.md).

## What this is

Grok Cloud Studio (GCS) is a **local control plane** for a named studio
floor. It is not a desktop agent OS, not a messaging gateway, and not a
plugin marketplace.

| Layer | Who | Runtime | Job |
|---|---|---|---|
| Directors / CCGS leads | First-class seats | Grok Build CLI mind (`grok --prompt-file`, Cursor CLI fallback) | Assign work, move tickets, collect PRs. Do not implement large diffs locally. |
| Orchestrator | Grok Bot seat (`skipSeats`) | Bot wake files, not ACP inject | Studio orchestrator. Never a Cursor CloudAgent. Never a grunt. |
| Grunts | Ephemeral specialists | Cursor Cloud Extra High (`grok-4.6`, `effort=xhigh`, `fast=false`) | Open PRs against `GCS_CLOUD_REPO`. Spawn only via `scripts/launch-cloud-extra-high.sh`. |
| Board | tcarac/taskboard v0.6.0 | Ticket CLI + HTTP `/mcp` | Mission control. Agent Kanban is gone. Hermes Kanban is not the board. |
| Bus | A2A hub | `inbox.jsonl` per seat | Seat-to-seat mail. MCP is agent-to-tool. |

Scale with **remote Extra High**, not more local `grok agent serve` processes.
A ~15GB box OOMs if the full registry becomes persistent ACP daemons.

## Hive diagram

```
send.sh → hub.py (ack + inbox JSONL)
            ↓
        mind.py         → grok --resume pinned UUID --prompt-file   (GCS_MIND_SEATS)
        wake-daemon.py  → seat-prompt-acp.sh --pin-session          (leftover GROW)
        dispatch.py     → leftover acp_inject.py                    (non-GROW only)

host-ticker.py → ACP_PING STATUS/CONTINUE (work turns, tools allowed; not a 45s assigner)

launch-cloud-extra-high.sh → Cursor Cloud Agent.create
                           → spawn-waiter.sh → A2A ping owning seat (FLEET_DONE / PR_READY)
```

Mind is mailbox + pin + stay-up. Python is **not** the agent. Grok (or Cursor
CLI after `MIND_SWITCH`) is the agent for that turn. Do not parse grok stdout
for function calls. Do not run a second Python tool loop. Do not copy
`GROK_HOME` MCP into Cursor CLI. Two catalogs. Never fake a transfer.

ACP `session/prompt` into `grok agent serve` is leftover host OS. Opted-in
mind seats do not use it.

## Seats (CCGS leads, not a 49-specialist floor)

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

Registry also has `cloud`, `qa-b`, `ops` (extract alias), and Bot
`orchestrator` / `donald` in `skipSeats`. **Do not add 49 specialists.**
Composer, mixer, foley, animator, quest-designer, lore-keeper, and the rest
of that roster stay Extra High grunts.

Palemon wipe: `docs/studio/WIPE.md`. `studio.env.example` staffs mind seats
for those leads. Generic extract starts with empty `GCS_MIND_SEATS`.

## Law (Directors)

- Never print or commit credentials (`CURSOR_API_KEY`, webhook secrets, ACP tokens).
- Directors and leads spawn specialists only via `scripts/launch-cloud-extra-high.sh`.
- After `CLOUD_LAUNCH_OK`, do not block on watch. The waiter A2A-pings the owning seat.
- RESULT is duplex, not success. Hub `TASK_STATE_COMPLETED` on `message:send` is a **receipt**, not proof the mind acted.
- Board is tcarac/taskboard. Do not reconnect Agent Kanban (`ak`).
- Mind runner default `GCS_MIND_RUNNER=auto`. On HTTP 402, flip once and retry **that same mail line**. Forced `grok|cursor` does not flip.
- Pin `mind/session` (grok UUID) and `mind/cursor-session` (Cursor chat id) separately. Do not remint because harvest was empty or because the runner switched.
- Ship gate: `.venv/bin/pytest -q` and `python3 scripts/secret_scan.py`.

## How this differs from Hermes (executive)

Hermes v0.21 is an **agent OS**: Bot Mode society, group chats, `hermes peer`,
cron with continuity, live `delegate_task` steer, desktop MCP command center,
in-app browser the agent drives, skills hub, memory providers, messaging
gateways, Kanban plugin.

GCS is a **studio control plane**: a small named floor of Grok Build
Directors, Extra High grunts for diffs, A2A mail, taskboard, and two-runtime
mind. Borrow mailbox ideas. Do not vendor the OS. Do not copy Bot Mode as 49
local seats. Do not copy Hermes Kanban, cron-as-assigner, desktop browser, or
the plugin SDK tree.

## What LIV-62 is / is not

| This ticket | Not this ticket |
|---|---|
| Linear document on Grok Cloud Studio | Vendoring `hermes-agent` |
| Gap analysis vs Hermes v0.21 | Copying Bot Mode, group chats, `message_agent` |
| Paste-ready hive law for Living Sky | Harvest PRs that port mailbox helpers into `mind.py` |
| Pointers to existing GCS law (`MIND.md`, `A2A.md`) | A 49-specialist registry |

Open harvest PRs (**#26**, **#28**) port selected mailbox ideas into code.
They are not this document. Merge them only if the floor wants those helpers
**inside the grok mailbox**, still without a Hermes tree.

## Linear paste

1. Living Sky → Documents → New document.
2. Title: **Grok Cloud Studio**.
3. Body: this file (or the executive section above plus a link to the PR).
4. Link issue **LIV-62**.
5. Do not paste Hermes README, `plugin.yaml`, or any Hermes source.

Linear MCP was not available in the cloud agent that filed this PR. This file
is the source of truth to paste.
