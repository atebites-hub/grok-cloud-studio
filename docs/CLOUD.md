# Cursor Cloud Extra High

See also `scripts/cloud/README.md`.

## Required env

```bash
export CURSOR_API_KEY=...          # or ~/.config/cursor/agent.env
export GCS_CLOUD_REPO=https://github.com/ORG/REPO
export GCS_CLOUD_REF=main          # optional
```

## Linear (Living Sky)

Cursor Cloud Extra High agents **cannot scrape `GROK_HOME`**. Give them Linear
via the cloud environment:

- Snapshot `LINEAR_API_KEY` from `$GCS_A2A_STATE/linear.env` (or Cursor
  dashboard Secrets). Never print or commit the key.
- Checkout `.cursor/mcp.json` is Linear HTTP (`https://mcp.linear.app/mcp`)
  plus taskboard only — not a copy of the Grok MCP catalog.

Palemon Linear is **Living Sky** (`linear.app/livingsky`, team Livingsky /
`LIV`). **NEVER Black Swan Money.**

## Launch

```bash
scripts/launch-cloud-extra-high.sh "Implement X. Open a PR." "short-name"
scripts/cloud/watch-cloud-agent.sh bc-...
scripts/cloud/result-cloud-agent.sh bc-...
```

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.

## Fleet capacity

Count latest-run `runStatus` (`RUNNING` / `CREATING`), not agent `status=ACTIVE`.
`ACTIVE`+`FINISHED` leftovers are not workers. `scripts/cloud/list-cloud-agents.sh`
prints `runStatus`. If playability/art work is in progress and the in-flight
count for `GCS_CLOUD_REPO` is below `GCS_CLOUD_RUNNING_CAP` (default 8), the
cloud mind **MUST** launch (`scripts/cloud/running-count.sh --work "…"`).
