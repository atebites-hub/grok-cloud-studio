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

## Fleet floor (LIV-41 / LIV-67)

Directors must `cloud_launch` until the target repo has **≥8** in-flight
runs (`GCS_CLOUD_MIN_RUNNING`, default 8). Count latest-run **`runStatus`**
(`RUNNING` / `CREATING`). Agent `status` stays `ACTIVE` until archive —
leftover `ACTIVE`+`FINISHED` shells are **not** workers.

`scripts/cloud/list.sh` / `status.sh` print `runStatus`. Check the floor
with `scripts/cloud/running-count.sh`. Never launch Bot CloudAgent
(orchestrator / donald); Bot is `send.sh`, not Extra High.
