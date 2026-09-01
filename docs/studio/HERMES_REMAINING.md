# LIV-62 remaining after #47

Living Sky **LIV-62**. In-repo investigation (no clone of
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)).
This is **not a copy of Hermes**. Do not vendor that tree.

First hive-upgrade is GCS [PR #47](https://github.com/atebites-hub/grok-cloud-studio/pull/47)
(LIV-63): mail-as-a-turn as grok mind, plus Extra High command-center tools
(`cloud_list` / `cloud_status` / `cloud_followup` / `cloud_result`) judged by
`runStatus=RUNNING`. Gap analysis lives on
[PR #43](https://github.com/atebites-hub/grok-cloud-studio/pull/43)
(`docs/studio/HERMES_GAP.md` on that branch). This file is what is **still
open on main after that first upgrade**.

## What #47 already closed

| Hermes v0.21 surface | After #47 |
|---|---|
| Mail is a turn (Agent Inbox → one CLI turn) | Exemplified as grok mind: `tests/features/liv63_hermes_mail_as_turn.feature` |
| MCP command-center scripts (list / status / followup / result) | studio-mind PATH wrappers on that branch; Extra High only |
| Named Directors + Extra High grunts | Already GCS hive law |

## What this PR closes (one remaining gap)

**Session pin + stay-up.** Hermes named agents keep identity while idle.
GCS grok mind is mailbox + pin + stay-up, but on main the UUID was created
only when grok first ran. Empty harvest left `mind/session` missing, so
stay-up had no pin.

Now `process_once` calls `load_or_create_session` even when `inbox.jsonl`
has no new line:

- Pin a uuid4 in `$GCS_A2A_STATE/<seat>/mind/session` once.
- A later empty harvest **does not remint**.
- First grok turn after idle uses `--session-id` of that pin; later turns
  `--resume` the same UUID.
- Empty ticks do **not** invent `mind/mail.txt` or `transcript.jsonl`.
- `session.minted` is still only after grok exit 0.
- Cursor chat id stays a **separate** pin (`mind/cursor-session`). Idle
  harvest does not call `create-chat`.

Executable example:
[`tests/features/liv62_hermes_pin_stay_up.feature`](../../tests/features/liv62_hermes_pin_stay_up.feature).

## Not this PR (do not land)

Do **not** vendor Hermes. Do **not** open a sibling harvest PR. Do **not**
land GCS **#26** and **#28**.

| Harvest marker | Why it stays out |
|---|---|
| `format_mail_turn` / mail envelope | #26/#28 |
| `filter_inbound_mail` / defang | #26/#28 |
| `MAIL_MAX_CHARS` 16k cap | #26/#28 |
| `mind/heartbeat` | #26/#28 stay-up liveness file. Pin is identity, not a heartbeat file. |
| Hub harvest envelope / COMPLETE-on-enqueue | #26/#28. Main already queues `TASK_STATE_SUBMITTED` until harvest (LIV-85). This remaining does not remint that law or add envelope/defang. ACK is still a receipt, not mind-turn done. |

Skip (intentional ≠): Bot Mode society, 49 specialist seats, Hermes Kanban,
copying `GROK_HOME` MCP into Cursor CLI, Grok Bot as the Extra High grunt,
ACP `session/prompt` as the opted-in mind path, cron-as-assigner, messaging
gateways, in-app browser, plugin SDK / `message_agent`.

## How this was investigated

No clone of Hermes. Sources:

- This repo: `scripts/directors/mind.py`, `docs/studio/MIND.md`,
  `scripts/directors/seat-mind-loop.sh`.
- GCS PR #43 matrix (GitHub file fetch, not a vendored tree).
- GCS PR #47 hive-upgrade + mail-as-a-turn BDD (does not land harvest).

Directors stay Grok Build. Specialists stay Cursor Cloud Extra High
(`grok-4.6`, `xhigh`, `fast=false`). Never Bot CloudAgent.
