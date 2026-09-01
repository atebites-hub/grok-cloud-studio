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
- Studio-ops 10-minute beat writes one Manning apply-log (LIV-71). `HEALTH_OK` is illegal without that beat's APPLY.

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

## Hive law — Manning apply-log (LIV-71)

Studio-ops 10-minute beat is not HEALTH_OK unless it applied a Manning
model to an IaC/Palemon change and wrote that apply to the dated log.

This hive is **Living Sky only**. Never launch Bot CloudAgent for this
law. This control plane does **not** ship Palemon game code. Extra High
grunts that change Palemon still target `GCS_CLOUD_REPO`. The apply-log
only records the model title plus the ops/IaC change.

## Law (LIV-71)

Each 10-minute beat (`GCS_TICKER_SEC` / `GCS_BEAT_SEC`, default 600)
**MUST** append one `APPLY` line to:

```text
studio-archive/log/YYYY-MM-DD.md
```

Default root: `$GCS_STUDIO_ARCHIVE` or `$GCS_A2A_STATE/studio-archive`.

`./health_check.sh` must **not** print `HEALTH_OK` when the current beat
has no apply-log line. Missing apply-log is `HEALTH_DEGRADED` (hub still
up) or stays `HEALTH_DOWN` if the hub is down.

Never paste copyrighted book text. Cite the **model name** (book title)
and the **IaC/Palemon change** only.

## Allowed models (titles only)

| Model | Apply as (our words, not book text) |
|---|---|
| Grokking Simplicity | Keep calculations out of IaC actions this beat |
| Think Distributed Systems | Treat failure, replication, and timeouts as first-class |
| Looks Good to Me | Keep the beat's diff small and reviewable |
| BDD in Action | Observable behavior: HEALTH_OK only with this beat's APPLY |
| Acing the System Design Interview | Isolate capacity, fail closed, do not grow the seat roster |

`scripts/studio/apply_log.py` rotates one title per beat when `--model`
is omitted. Unknown titles are rejected.

## Line format

```text
- APPLY beat=2026-09-01T15:50Z seat=studio-ops model=BDD in Action change=IaC: bus=ok; Palemon: no game code
```

`beat=` is the UTC window floored to 10 minutes. One APPLY per beat
(idempotent). `change=` must include both `IaC` and `Palemon` and stay
under 240 characters.

## Who writes

`scripts/directors/watchdog-studio-ops.sh` appends at the end of every
10-minute studio-ops beat (`python3 scripts/studio/apply_log.py beat`).
Studio-ops mind/SOUL still owns the law if the watchdog is down: do not
claim health without the line.

## Check

```bash
python3 scripts/studio/apply_log.py beat --change 'IaC: …; Palemon: …'
python3 scripts/studio/apply_log.py check
./health_check.sh
```
