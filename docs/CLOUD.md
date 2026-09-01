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

Never Grok Bot CloudAgent. Create **and** `agent.send` (first run and follow-up)
pin grok-4.6 xhigh; there is no env override. If the create or send response
exposes a model that is not `grok-4.6` (dashboard alias `cursor-grok-4.6-xhigh`),
launch prints `CLOUD_LAUNCH_ERR` and does not count the agent as a worker.

Set the Cursor dashboard Cloud Agent default to grok-4.6 xhigh so Auto cannot
pick Sonnet or Gemini.

## List live workers

`scripts/cloud/list-cloud-agents.sh` prints `runStatus` (`RUNNING` vs `FINISHED`)
and `model=` when the API exposes it. Agent `status=ACTIVE` leftover +
`runStatus=FINISHED` is not a worker.

Staff each active `GCS_CLOUD_REPO` until `>= GCS_CLOUD_MIN_RUNNING` (default 8)
`RUNNING`. `scripts/cloud/running-count.sh` prints `CLOUD_MUST_LAUNCH=1` while
below that floor.
