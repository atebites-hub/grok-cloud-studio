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

MCP `cloud_list` (`plugins/cursor-cloud`, `scripts/cloud/list_helper.py`) prints latest-run `runStatus` (`RUNNING` vs `FINISHED`) next to agent `status`. Cursor Cloud agents stay `ACTIVE` until archive, so leftover `ACTIVE`+`FINISHED` rows are not live workers. This is independent of bash `list.sh`.
