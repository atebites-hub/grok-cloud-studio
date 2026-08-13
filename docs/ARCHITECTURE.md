# Grok Cloud Studio — Architecture

Public control plane for multi-seat Grok Build Directors + Cursor Cloud Extra High coding grunts.

## Surfaces

| Surface | Role |
|---|---|
| **A2A hub** (`scripts/a2a/`) | Agent-to-agent messaging between Director seats |
| **ACP seat daemons** (`scripts/directors/`) | Persistent `grok agent serve` sessions; A2A injects work |
| **Cloud Extra High SDK** (`scripts/cloud/`) | Launch/status/watch/followup/result for Cursor Cloud Agents |
| **Fleet shepherd** | Slow-poll safety net; A2A `FLEET_DONE` / `PR_READY` when runs go terminal |
| **Webhook harness** (`scripts/webhook/`) | Optional signed FINISHED/ERROR → A2A ping (+ local simulate) |
| **MCP plugins** (`plugins/`) | Thin stdio wrappers: `a2a_*`, `cloud_*` |

## Data flow

1. Ops / Director decides work.
2. `scripts/launch-cloud-extra-high.sh` creates an Extra High grunt (`GCS_CLOUD_REPO` required).
3. bc-id is recorded on the seat fleet ledger under `.a2a-state/<seat>/` (runtime only; not shipped).
4. Waiter / webhook / fleet-shepherd notifies the owning seat via A2A.
5. Seat collects `result-cloud-agent.sh`, hands PR to QA.

## Env prefix

Prefer `GCS_*`. Some scripts historically used `PALEMON_*`; this public extract uses `GCS_*`.

## Security

- Never commit `.env`, `agent.env`, `auth.json`, `acp.secret`, `.a2a-state`, or API keys.
- Ship `.env.example` placeholders only.
- Scripts must never print secret values.

Repo: https://github.com/atebites-hub/grok-cloud-studio
