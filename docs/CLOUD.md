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
scripts/cloud/followup-cloud-agent.sh bc-... "Keep the PR; fix the failing check."
```

Follow-up **REFUSE**s when the latest `runStatus` is `RUNNING` (do not stack a second run on a live Extra High). Leftover `ACTIVE`+`FINISHED` shells may be followed up. Never Bot CloudAgent.

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.
