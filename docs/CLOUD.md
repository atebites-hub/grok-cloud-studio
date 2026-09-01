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

Capacity beats must call `scripts/cloud/occupancy-count.sh` (SDK `Agent.list` + `Agent.listRuns`, REST analog `GET /v1/agents/{id}/runs`). Existence **ACTIVE/IDLE** is not liveness. Fan-out is **bounded** (`CLOUD_OCCUPANCY_CONCURRENCY`, default 8) with a per-call timeout (`CLOUD_LIST_RUNS_TIMEOUT_SEC`, default 15s, cap 15) and an overall deadline (`CLOUD_OCCUPANCY_DEADLINE_SEC`, default 30s). Probe **ERR/timeout is fail-closed**: `CLOUD_OCCUPANCY_ERR reason=timeout|err|deadline` and a non-zero exit — never a fake `running=0` that would either hang the beat or over-launch. Success prints `CLOUD_OCCUPANCY running=N leftover_active=N creating=N listed=N`. `GCS_BOT_AGENT_ID` is skipped (never Bot CloudAgent). Palemon Linear is Living Sky (`LIV`).

## Directors-spawn law (LIV-41)

Directors and leads spawn specialists only via
`scripts/launch-cloud-extra-high.sh`. Extra High create stays **grok-4.6**,
`effort=xhigh`, `fast=false`. Never Bot CloudAgent (orchestrator / donald);
Bot is `send.sh`, not Extra High.

Count latest-run **`runStatus`** (`RUNNING` / `CREATING`) for
`GCS_CLOUD_REPO`. Leftover `ACTIVE`+`FINISHED` shells are **not** workers.

If **playability** work is in progress and that RUNNING Extra High count is
below **8** (`GCS_CLOUD_MIN_RUNNING`), cloud mind **MUST** call
`scripts/launch-cloud-extra-high.sh`.

Do **not** reuse `--name gcs-liv41-mind-must-launch` — that name is already
RUNNING. Pick a new Extra High name.

Palemon Linear is **Living Sky** (`LIV`), never Black Swan.

Helper: `scripts/cloud/directors_spawn.py` (`cloud_mind_spawn_if_required`).
