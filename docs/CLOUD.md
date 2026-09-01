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
scripts/cloud/watch-cloud-agent.sh bc-...
scripts/cloud/result-cloud-agent.sh bc-...
```

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.

## List (capacity)

`scripts/cloud/list-cloud-agents.sh` prints one compact row per agent:

`id=… status=… runStatus=… prUrl=… name=… url=… latestRunId=…`

`status=ACTIVE` is leftover membership until archive. Count `runStatus=RUNNING` for live Extra High capacity. `prUrl` is on the same row so Directors do not N-serial `status.sh`. Latest runs are fetched in parallel (`ThreadPoolExecutor` / `Promise.all`).

Never launch Bot as a CloudAgent (orchestrator is `scripts/a2a/send.sh`). Living Sky Linear is `LIV-*`.
