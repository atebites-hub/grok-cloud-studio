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

## Capacity beat

Count only latest-run **`runStatus=RUNNING`**. Agent `status=ACTIVE` leftovers (`FINISHED` shells) are not workers. Bound remotes (`GCS_CLOUD_REPO` / `GCS_CLOUD_REPOS` and `GCS_GAME_REPO`) are counted separately. Floor is `GCS_CLOUD_MIN_RUNNING` (default 8). Opted-in mind seats **MUST** call `scripts/launch-cloud-extra-high.sh` on a capacity beat (`ACP_PING`, `CAPACITY_BEAT`, studio-mind `cloud_capacity`) until that floor. Never Bot CloudAgent. Living Sky Linear is **LIV**, not Black Swan.

This is the mind / studio-mind slice. It does not remint `list.sh --repo`.
