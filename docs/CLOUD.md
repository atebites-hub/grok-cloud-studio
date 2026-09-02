# Cursor Cloud Extra High

See also `scripts/cloud/README.md`.

## Required env

```bash
export CURSOR_API_KEY=...          # or ~/.config/cursor/agent.env
export GCS_CLOUD_REPO=https://github.com/ORG/REPO
export GCS_CLOUD_REF=main          # optional
```

## Linear (Living Sky)

Cursor Cloud Extra High agents **cannot scrape `GROK_HOME`**. They get Linear
via the cloud environment (cloud-env snapshot / dashboard Secrets / process
env):

- Set `LINEAR_API_KEY` on the Cursor Cloud snapshot or Secrets. Never print
  or commit the key.
- Checkout `.cursor/mcp.json` is Linear HTTP (`https://mcp.linear.app/mcp`)
  plus taskboard only — not a copy of the Grok MCP catalog.
- RUNNING specialists `save_comment` on Living Sky issues
  (`linear.app/livingsky`, team Livingsky / `LIV`). **NEVER Black Swan Money.**

Grok Build minds get Linear via seat `GROK_HOME/config.toml` (separate
catalog). See `docs/studio/MIND.md`.

## Launch

```bash
scripts/launch-cloud-extra-high.sh "Implement X. Open a PR." "short-name"
# CLOUD_LAUNCH_OK — do not watch. The SDK waiter A2A-pings the owning seat
# and REPORT_TO (default studio-ops). Collect on FLEET_DONE:
scripts/cloud/result-cloud-agent.sh bc-...
```

Directors (`GCS_DIRECTOR_SEAT` set) get `CLOUD_WATCH_REFUSED` from
`watch.sh` / `watch-cloud-agent.sh` unless `CLOUD_ALLOW_BLOCK_WAIT=1`.

Launch `--name` **REFUSE**s when a live `runStatus=RUNNING` Extra High already has that name (no twin remint). Leftover `ACTIVE`+`FINISHED` does not block. Name-matched Extra High whose latest runStatus cannot be read is fail-closed (no create). Never Bot CloudAgent.

Palemon Linear is Living Sky (`LIV`).

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.

MCP `cloud_list` (`plugins/cursor-cloud`, `scripts/cloud/list_helper.py`) prints latest-run `runStatus` (`RUNNING` vs `FINISHED`) next to agent `status`. Cursor Cloud agents stay `ACTIVE` until archive, so leftover `ACTIVE`+`FINISHED` rows are not live workers. This is independent of bash `list.sh`.

Fail-closed (LIV-67 / LIV-69): create **and** send/followup always pin grok-4.6 xhigh `fast=false`. Any `CURSOR_CLOUD_MODEL` that is not exactly `grok-4.6` is **rejected** (no create, no send). REST list/runs omit model; omitted send uses dashboard Auto (Jay saw Opus 5). Never Bot CloudAgent. Do not merge empty CI.

MERGE_REQUEST / QA: empty GitHub leftover-green is not a ship-gate. Require pasted `.venv/bin/pytest -q` (`N passed`) and `python3 scripts/secret_scan.py` (`secret_scan=clean`). `python3 scripts/cloud/pr_evidence.py judge` is the gate; a GitHub check name is not a substitute. Do not squash-merge CONFLICTING PRs.

`scripts/cloud/list.sh` / `list-cloud-agents.sh` print agent `status` (membership, often `ACTIVE`) and latest-run `runStatus` (`RUNNING` vs `FINISHED`). Agent `ACTIVE` is not a live worker. Leftover `ACTIVE`+`FINISHED` must not count as live.

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
