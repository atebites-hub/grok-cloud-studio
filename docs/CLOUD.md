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

## LIV-41 directors-spawn (FAIL closed)

Directors and leads spawn specialists only via
`scripts/launch-cloud-extra-high.sh` or the `cloud_launch` plugin. Extra High
create stays **grok-4.6**, `effort=xhigh`, `fast=false`. Never Bot CloudAgent
(orchestrator / donald). Do not have Donald DIY Extra High.

Count latest-run **`runStatus=RUNNING`** for `GCS_CLOUD_REPO`. Leftover
`ACTIVE`+`FINISHED` shells are **not** workers. Floor is **8**
(`GCS_CLOUD_MIN_RUNNING`).

A spawn-required director turn (ACP_PING / LAUNCH / TASK_ASSIGN / playability)
that does not invoke the launcher when RUNNING is under 8 is **FAIL**.
Demonstrate, don't theatre. Do **not** reuse `--name gcs-liv41-mind-must-launch`.

Studio Linear is **Living Sky** (`LIV`), never Black Swan. Judge:
`scripts/directors/director_turn_spawn.py`. Feature:
`docs/studio/bdd/liv41_directors_spawn.feature`.
