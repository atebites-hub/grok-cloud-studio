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

Per-invocation `GCS_CLOUD_REPO` wins over a process-global `CURSOR_CLOUD_REPO` and over `agent.env`. Prefix the var on that command only; the launcher does not export it, so the next launch keeps the original default (studio vs Palemon). Specialists are Cursor Cloud Extra High, not a Grok Bot grunt.
