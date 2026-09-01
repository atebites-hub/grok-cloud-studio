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

## List (per-repo)

```bash
scripts/cloud/list-cloud-agents.sh --repo org/name
scripts/cloud/list.sh --repo https://github.com/ORG/REPO
```

Each row prints agent `status` (membership; leftover `ACTIVE` until archive)
and latest-run `runStatus` (`RUNNING` vs `FINISHED` / `none`). Count live
workers with `runStatus=RUNNING` for the bound repo. Do not treat leftover
`ACTIVE` as capacity.

Palemon Linear is Living Sky (`LIV`), not Black Swan. Never Bot CloudAgent.
