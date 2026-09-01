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
scripts/cloud/status-cloud-agent.sh --ids bc-...,bc-...
scripts/cloud/watch-cloud-agent.sh bc-...
scripts/cloud/result-cloud-agent.sh bc-...
```

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.

`status.sh` / `status-cloud-agent.sh` take multiple bc-ids or `--ids a,b,c` and print **`runStatus`** on the same line as `id=` (latest run, not leftover agent `ACTIVE`). Fetches run in parallel so capacity beats do not serial-timeout `get_agent_run`. Do not remint `list.sh` runStatus (GCS #29). Never Bot CloudAgent.
