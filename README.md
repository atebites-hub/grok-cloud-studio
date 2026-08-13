# Grok Cloud Studio

Secret-free control plane for **Grok Build CLI seats** (Directors) plus **Cursor Cloud Extra High** coding grunts.

This repository is the public extract: A2A hub, ACP seat daemons, Extra High SDK wrappers, waiter, orphan fleet-shepherd, MCP plugins, and a signed webhook harness. It is not a game client. Point Extra High at **your** git repo with `GCS_CLOUD_REPO` / `CLOUD_REPO_URL`.

## What you get

| Piece | Path |
|---|---|
| A2A hub / send / dispatch / bus | `scripts/a2a/` |
| ACP seat daemons + inject | `scripts/directors/start-seat-daemon.sh`, `acp_inject.py` |
| Extra High SDK + bash wrappers | `scripts/cloud/sdk/`, `scripts/launch-cloud-extra-high.sh` |
| Waiter (`run.wait` → A2A ping) | `scripts/cloud/spawn-waiter.sh`, `sdk/wait-notify.ts` |
| Orphan fleet-shepherd | `scripts/directors/fleet-shepherd.py` |
| MCP plugins | `plugins/a2a`, `plugins/cursor-cloud` |
| Webhook harness | `scripts/cloud/webhook_receiver.py`, `webhook-harness.sh` |
| Agent Kanban (sync-only) | `docs/studio/AGENT_KANBAN.md`, `scripts/studio/agent-kanban/` |
| Seat lifecycle | `scripts/a2a/seat-lifecycle.sh`, `docs/studio/a2a/SEAT_LIFECYCLE.md` |

Example seats (edit `docs/a2a/registry.json`): `floor`, `ops`, `cloud`, `qa-a`, `qa-b`. Hub: `127.0.0.1:8732`. ACP ports: `8740+`.

## Quick start

```bash
git clone https://github.com/atebites-hub/grok-cloud-studio
cd grok-cloud-studio
./install.sh
cp .env.example .env   # fill GCS_CLOUD_REPO; never commit .env
./doctor.sh

# Local bus (hub + dispatch + orphan shepherd). ACP daemons are opt-in.
scripts/a2a/start-studio-bus.sh start
# scripts/a2a/start-studio-bus.sh start --daemons   # grok agent serve per seat

scripts/a2a/send.sh floor "hello from ops"
```

Launch Extra High (requires `CURSOR_API_KEY` in the environment or `~/.config/cursor/agent.env`):

```bash
export GCS_CLOUD_REPO="https://github.com/example/your-repo"
scripts/launch-cloud-extra-high.sh "Implement the assigned outcome. Open a PR." "floor-demo"
# CLOUD_LAUNCH_OK id=bc-…  — waiter pings the owning seat when the run finishes
```

## Environment

See `.env.example`. Prefix is **`GCS_*`**. Important:

- `GCS_CLOUD_REPO` / `CLOUD_REPO_URL` — **required** for Extra High create (fail closed)
- `GCS_CLOUD_REF` — default `main`
- `GCS_SPAWN_WAITER=0` — disable the detached waiter (tests)
- `GCS_WEBHOOK_SECRET` — enable signed webhook receiver
- `GCS_AGENT_KANBAN_API_KEY` / `AGENT_KANBAN_API_KEY` — optional Agent Kanban (never print)
- `GCS_AK_BRIDGE=0` — force-disable bus ak-bridge
- `CURSOR_API_KEY` — never print; never commit

## MCP plugins

```bash
grok plugin install ./plugins/a2a --trust
grok plugin install ./plugins/cursor-cloud --trust
```

Tools: `a2a_list_seats`, `a2a_send`, `cloud_launch`, `cloud_status`, `cloud_result`. Details: `docs/PLUGINS.md`.

## Tests + secret scan

```bash
.venv/bin/pytest -q
python3 scripts/secret_scan.py
```

The secret scan fails closed on credentials, private-key blocks, and product lore that does not belong in this public control plane.

## License

MIT. See `LICENSE`.
