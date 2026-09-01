# Cursor Cloud Extra High

See also `scripts/cloud/README.md`.

## Required env

```bash
export CURSOR_API_KEY=...          # or ~/.config/cursor/agent.env
export GCS_CLOUD_REPO=https://github.com/ORG/REPO
export GCS_CLOUD_REF=main          # optional
```

## Launch

```bash
scripts/launch-cloud-extra-high.sh "Implement X. Open a PR." "short-name"
scripts/cloud/watch-cloud-agent.sh bc-...
scripts/cloud/result-cloud-agent.sh bc-...
```

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.

## Optional webhook (statusChange)

`FLEET_DONE` can arrive from a signed Cursor Cloud `statusChange` POST instead of waiter `get_agent_run` polling.

See `scripts/cloud/README.md` (Optional Cursor Cloud webhook). Set `GCS_WEBHOOK_SECRET`, run `scripts/a2a/start-studio-bus.sh start` (or `webhook-harness.sh serve`), and point Cursor at:

```
POST /webhooks/cursor-cloud
X-Webhook-Signature: sha256=<hex>
```

Official payload: `id`, `status`, `target.prUrl` — https://cursor.com/docs/cloud-agent/api/webhooks

Waiter remains the fallback when the secret is unset. Extra High create stays v1 grok-4.6 xhigh `fast=false`.
