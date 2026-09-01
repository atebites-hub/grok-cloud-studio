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

Launch `--name` **REFUSE**s when a live `runStatus=RUNNING` Extra High already has that name (no twin remint). Leftover `ACTIVE`+`FINISHED` does not block. Name-matched Extra High whose latest runStatus cannot be read is fail-closed (no create). Never Bot CloudAgent.

Palemon Linear is Living Sky (`LIV`).

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.

Fail-closed (LIV-67 / LIV-69): create **and** send/followup always pin grok-4.6 xhigh `fast=false`. Any `CURSOR_CLOUD_MODEL` that is not exactly `grok-4.6` is **rejected** (no create, no send). REST list/runs omit model; omitted send uses dashboard Auto (Jay saw Opus 5). Never Bot CloudAgent. Do not merge empty CI.

`scripts/cloud/list.sh` / `list-cloud-agents.sh` print agent `status` (membership, often `ACTIVE`) and latest-run `runStatus` (`RUNNING` vs `FINISHED`). Agent `ACTIVE` is not a live worker. Leftover `ACTIVE`+`FINISHED` must not count as live.
