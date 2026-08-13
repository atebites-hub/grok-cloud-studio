# Agent Kanban — studio mission control

Grok Cloud Studio mirrors Extra High fleet rows onto an [Agent Kanban](https://agent-kanban.dev) board. This is **sync-only mission control**: the local A2A bus may run `fleet-bridge.py` as an observer (`ak create task` + status transitions). It does **not** start the Agent Kanban worker daemon.

Upstream CLI/source: [github.com/saltbo/agent-kanban](https://github.com/saltbo/agent-kanban). License: **FSL-1.1-ALv2** (Functional Source License, converting to Apache 2.0 after two years). You can use, modify, and self-host; you cannot offer a competing hosted service. See the upstream `LICENSE`.

The local HTML dashboard under `scripts/studio/dashboard/` is **LEGACY**. Use this board instead.

## Board

Default board title is assembled at runtime (`Pale`+`mon Studio`) unless you set `AGENT_KANBAN_BOARD_NAME` / `GCS_AGENT_KANBAN_BOARD_NAME`. Board type is `ops` (tracking, not AK worker dispatch).

```bash
export AGENT_KANBAN_BOARD_NAME="Studio Mission Control"
```

## Sync-only (do not `ak start` by default)

| Do | Do not |
|---|---|
| `ak config set`, `ak get board`, `ak create board/task`, `ak task claim/review/complete` | `ak start` / `ak stop` as part of the studio bus |
| Mirror `.a2a-state/*/fleet.jsonl` (+ events) → AK Tasks | Claim studio seats or spawn AK workers from this repo |
| Keep keys out of logs and git | Print `AGENT_KANBAN_API_KEY` / `GCS_AGENT_KANBAN_API_KEY` |

Directors still launch Extra High with `scripts/launch-cloud-extra-high.sh`. Agent Kanban is a view of that fleet, not a second dispatcher. If you want the upstream daemon, run `ak start` yourself — it is **opt-in and not wired into** `start-studio-bus.sh`.

## Environment

Primary names are `AGENT_KANBAN_*`. Grok Cloud Studio aliases are `GCS_AGENT_KANBAN_*` / `GCS_AK_*`.

| Variable | Alias | Purpose |
|---|---|---|
| `AGENT_KANBAN_API_KEY` | `GCS_AGENT_KANBAN_API_KEY` | Machine API key (never print / never commit) |
| `AGENT_KANBAN_API_URL` | `GCS_AGENT_KANBAN_API_URL` | Default `https://agent-kanban.dev` |
| `AGENT_KANBAN_BOARD_NAME` | `GCS_AGENT_KANBAN_BOARD_NAME` | Board title override |
| `AGENT_KANBAN_BOARD_ID` | `GCS_AGENT_KANBAN_BOARD_ID` | Skip lookup when set |
| `AGENT_KANBAN_GITHUB_REPO` | `GCS_AGENT_KANBAN_GITHUB_REPO` | Optional git remote to register |
| `AGENT_KANBAN_BIN` | `GCS_AGENT_KANBAN_BIN` | CLI name, default `ak` |
| `AGENT_KANBAN_CONNECTOR_SECRETS` / `AGENT_KANBAN_SECRET_PATH` | `GCS_AGENT_KANBAN_*` | Path or JSON blob with `api_key` |
| `AK_BRIDGE_POLL_SEC` | `GCS_AK_POLL_SEC` / `GCS_AK_BRIDGE_POLL_SEC` | Fleet poll interval (default 5s) |
| — | `GCS_AK_BRIDGE` | `1` force-on / `0` force-off bus ak-bridge |
| — | `GCS_AK_DRY` | Dry-run observer (no mutate) |

Key resolution order for `configure-ak.sh`: `AGENT_KANBAN_API_KEY`, then `GCS_AGENT_KANBAN_API_KEY`, then connector-secrets JSON `api_key` (file or blob). Connector file default: `.a2a-state/agent-kanban/connector-secrets.json`.

## Install / configure / bootstrap

Run install-ak.sh, configure-ak.sh, then bootstrap-board.sh under scripts/studio/agent-kanban/.

configure-ak.sh writes .a2a-state/agent-kanban/configured (mirrored under kanban/) with timestamp and api-url only (never the key). bootstrap-board.sh writes board.id + board.json.

## Fleet bridge + events

scripts/studio/agent-kanban/fleet-bridge.py polls .a2a-state/*/fleet.jsonl and events.jsonl, creates tasks, walks status (todo -> in_progress -> in_review -> done / cancelled), and stores ids in .a2a-state/kanban/task-map.json (mirrored under agent-kanban/). Logs are AK_BRIDGE_* (seat, bc-id, task id — no secrets).

Examples: python3 scripts/studio/agent-kanban/fleet-bridge.py --once
and python3 scripts/studio/agent-kanban/fleet-bridge.py --once --dry-run

notify-event.sh appends observer events (hooked from spawn-waiter.sh on Extra High launch).

Status map: launched/open -> in progress; PR open -> in review; done/merged/closed+notified -> done; ERROR/CANCELLED -> cancelled.

## Studio bus

When AGENT_KANBAN_API_KEY / GCS_AGENT_KANBAN_API_KEY is set, or .a2a-state/agent-kanban/configured exists, or GCS_AK_BRIDGE=1, scripts/a2a/start-studio-bus.sh starts/stops/status the fleet bridge. Missing CLI or a crash is non-fatal. The bus never invokes ak start.

## Seat lifecycle + hardening

- Seat control plane: scripts/a2a/seat-lifecycle.sh (alias scripts/directors/lifecycle-seat.sh) — see docs/studio/a2a/SEAT_LIFECYCLE.md
- Crash recovery checklist: docs/studio/directors/HARDENING.md
- Handoff smoke (dry): scripts/cloud/smoke-handoff.sh

## Legacy dashboard

See scripts/studio/dashboard/README.md — LEGACY pointer back here.
