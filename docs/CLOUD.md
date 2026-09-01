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
scripts/cloud/list-cloud-agents.sh
scripts/cloud/status-cloud-agent.sh bc-...
scripts/cloud/followup-cloud-agent.sh bc-... "Keep the PR; fix the failing check."
scripts/cloud/result-cloud-agent.sh bc-...
# Do not block the Director turn on watch; the waiter A2A-pings on terminal.
```

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.
