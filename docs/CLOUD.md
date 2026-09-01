# Cursor Cloud Extra High

See also `scripts/cloud/README.md`.

## Required env

```bash
export CURSOR_API_KEY=...          # or ~/.config/cursor/agent.env
export GCS_CLOUD_REPO=https://github.com/ORG/REPO
export GCS_CLOUD_REF=main          # optional
# GCS_CLOUD_MIN_RUNNING=8          # playability/art RUNNING floor
```

`LINEAR_API_KEY` is **not** committed. Snapshot the cloud environment with
that env var set from a secret file (`scripts/cloud/load-linear-env.sh`,
`$LINEAR_API_KEY_FILE`, `$GCS_A2A_STATE/secrets/linear.api_key`, or
`~/.config/linear/api_key`). Cursor Cloud agents cannot scrape seat
`GROK_HOME`; they load Linear from checkout `.cursor/mcp.json` (Linear +
taskboard only) using snapshot `LINEAR_API_KEY`. Product Linear is Living
Sky (`linear.app/livingsky`, team Livingsky / LIV). Never Black Swan Money.

## Launch

```bash
scripts/launch-cloud-extra-high.sh "Implement X. Open a PR." "short-name"
scripts/cloud/running.sh --work-kind playability
scripts/cloud/watch-cloud-agent.sh bc-...
scripts/cloud/result-cloud-agent.sh bc-...
```

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.

## Cloud floor (must launch)

If playability or art work is in progress and `runStatus=RUNNING` count for
`GCS_CLOUD_REPO` is below `GCS_CLOUD_MIN_RUNNING` (default 8), the cloud mind
**MUST** launch. Do not burn Grok turns instead of spawning. Do not treat
`ACTIVE` + `FINISHED` leftovers as workers. Always print `runStatus`.
