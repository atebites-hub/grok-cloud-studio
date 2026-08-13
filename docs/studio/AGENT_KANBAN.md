# Agent Kanban — studio mission control

Grok Cloud Studio mirrors Extra High fleet rows onto an [Agent Kanban](https://agent-kanban.dev) board. This is **sync-only mission control**: the local A2A bus may run `fleet-bridge.py` to `ak apply` Task YAML. It does **not** start the Agent Kanban worker daemon.

Upstream CLI/source: [github.com/saltbo/agent-kanban](https://github.com/saltbo/agent-kanban). License: **FSL-1.1-ALv2** (Functional Source License, converting to Apache 2.0 after two years). You can use, modify, and self-host; you cannot offer a competing hosted service. See the upstream `LICENSE`.

The local HTML dashboard under `scripts/studio/dashboard/` is **LEGACY**. Use this board instead.

## Board

Default board title is studio mission control. Scripts assemble the product studio title at runtime (`Pale`+`mon Studio`) unless you set `AGENT_KANBAN_BOARD_NAME`. Board type is `ops` (tracking, not AK worker dispatch).

Override:

```bash
export AGENT_KANBAN_BOARD_NAME="Studio Mission Control"
```

## Sync-only (do not `ak start` by default)

| Do | Do not |
|---|---|
| `ak config set`, `ak get board`, `ak create board`, `ak apply -f` | `ak start` / `ak stop` as part of the studio bus |
| Mirror `.a2a-state/*/fleet.jsonl` → Task YAML | Claim, complete, or spawn AK workers from this repo |
| Keep keys out of logs and git | Print `AGENT_KANBAN_API_KEY` / `GCS_AGENT_KANBAN_API_KEY` |

Directors still launch Extra High with `scripts/launch-cloud-extra-high.sh`. Agent Kanban is a view of that fleet, not a second dispatcher. If you want the upstream daemon, run `ak start` yourself on the studio box — it is **opt-in and not wired into** `start-studio-bus.sh`.

## Environment

Primary names are `AGENT_KANBAN_*`. Grok Cloud Studio aliases are `GCS_AGENT_KANBAN_*`.

| Variable | Alias | Purpose |
|---|---|---|
| `AGENT_KANBAN_API_KEY` | `GCS_AGENT_KANBAN_API_KEY` | Machine API key (never print / never commit) |
| `AGENT_KANBAN_API_URL` | `GCS_AGENT_KANBAN_API_URL` | Default `https://agent-kanban.dev` |
| `AGENT_KANBAN_BOARD_NAME` | `GCS_AGENT_KANBAN_BOARD_NAME` | Board title override |
| `AGENT_KANBAN_GITHUB_REPO` | `GCS_AGENT_KANBAN_GITHUB_REPO` | Optional git remote to register if `ak create repo` works |
| `AGENT_KANBAN_BIN` | `GCS_AGENT_KANBAN_BIN` | CLI name, default `ak` |
| `AGENT_KANBAN_CONNECTOR_SECRETS` | `GCS_AGENT_KANBAN_CONNECTOR_SECRETS` | Path or JSON blob with `api_key` |
| `AK_BRIDGE_POLL_SEC` | `GCS_AK_BRIDGE_POLL_SEC` | Fleet poll interval (default 15s) |

Key resolution order for `configure-ak.sh`: `AGENT_KANBAN_API_KEY`, then `GCS_AGENT_KANBAN_API_KEY`, then connector-secrets JSON `api_key` (file or blob). Connector file default: `.a2a-state/agent-kanban/connector-secrets.json`.

## Install / configure / bootstrap

```bash
scripts/studio/agent-kanban/install-ak.sh      # npm install -g agent-kanban (90s timeout); no-op if ak exists
scripts/studio/agent-kanban/configure-ak.sh    # ak config set; write configured (ts + api-url only); smoke ak get board
scripts/studio/agent-kanban/bootstrap-board.sh # find/create board; optional repo register; print BOARD_URL
```

`configure-ak.sh` writes `.a2a-state/agent-kanban/configured` with **timestamp and api-url only** (never the key). `bootstrap-board.sh` writes `.a2a-state/agent-kanban/board.id`.

If `ak create repo` is supported, bootstrap registers the private product GitHub remote (URL assembled at runtime; override with `AGENT_KANBAN_GITHUB_REPO`). Failure to register is non-fatal.

## Fleet bridge

`scripts/studio/agent-kanban/fleet-bridge.py` polls `.a2a-state/*/fleet.jsonl`, applies Task YAML via `ak apply -f`, and stores ids in `.a2a-state/agent-kanban/task-map.json`. Logs are `AK_BRIDGE_*` (seat, bc-id, task id — **no secrets**).

```bash
python3 scripts/studio/agent-kanban/fleet-bridge.py --once
```

## Studio bus

When `AGENT_KANBAN_API_KEY` or `GCS_AGENT_KANBAN_API_KEY` is set, or `.a2a-state/agent-kanban/configured` exists, `scripts/a2a/start-studio-bus.sh` starts/stops/status the fleet bridge like bot-bridge. Missing CLI or a crash is **non-fatal** (hub/dispatch still run). The bus never invokes `ak start`.

## Legacy dashboard

See `scripts/studio/dashboard/README.md` — LEGACY pointer back here.
