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

## LIV-41 own-grunt (FAIL closed)

A director-owns-launch turn without spawning/watching its own Cursor Cloud
grunt via `scripts/launch-cloud-extra-high.sh` is FAIL (`reason=no-spawn-watch`).
Unique `--name` (example `gcs-liv41-own-grunt-floor2105`). Refuse twin of
RUNNING `gcs-liv59-anti-twin-floor2105`. Never Bot CloudAgent. Do not block
on `watch-cloud-agent.sh`; the waiter is `spawn-waiter.sh`. `GCS_SPAWN_WAITER=0`
is FAIL. Empty GitHub checks are not merge.
