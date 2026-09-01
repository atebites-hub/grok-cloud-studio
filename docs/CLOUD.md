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

## Capacity floor (LIV-67)

```bash
scripts/cloud/capacity-count.sh
scripts/cloud/capacity-count.sh --repo org/name
```

Prints `CLOUD_CAPACITY repo=org/name running=N floor=8 leftover_active=N must_launch=0|1 deficit=N`.

Count latest-run **`runStatus=RUNNING`** per bound git remote. Leftover agent
`status=ACTIVE` with `runStatus=FINISHED` is membership, not capacity.
`CREATING` is not `RUNNING`. Capacity beats (`ACP_PING STATUS/CONTINUE`)
call this helper so they skip leftover ACTIVE shells and keep launching
until `GCS_CLOUD_MIN_RUNNING` (default 8).

This is the per-repo RUNNING floor. It does not remint GCS #78 / #73 / #82
list running filters. Never Bot CloudAgent. Model stays grok-4.6 xhigh
`fast=false`.
