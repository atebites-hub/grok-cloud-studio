# Cursor Cloud Extra High control plane

**Audience:** Grok Cloud Studio Directors (and QA for rebase-only Extra High)  
**Auth:** `CURSOR_API_KEY` via env or `~/.config/cursor/agent.env` (never print)  
**Canonical:** `@cursor/sdk` in `scripts/cloud/sdk/` (Node **>= 22.13**)  
**REST:** `https://api.cursor.com/v1/agents` curl is **fallback only**  
**Model default (create):** `grok-4.6` + `effort=xhigh` via `scripts/launch-cloud-extra-high.sh`

These scripts do **not** spawn VM `cursor-grok` processes.

Architecture: Grok Build CLI seats = Directors; Cursor Cloud Extra High = coding grunts.  
MCP = tools; A2A = Director↔Director. See `docs/ARCHITECTURE.md`.

## Scripts

Directors keep calling these bash entrypoints. They route through `scripts/cloud/sdk/run.sh` unless REST is selected. The TypeScript uses `@cursor/sdk` (`Agent.create` / `resume` / `list` / `get` / `send` / `wait`).

| Script | Purpose |
|---|---|
| `../launch-cloud-extra-high.sh --name NAME "prompt"` | Create Extra High agent + initial run (PR auto). Prints `CLOUD_LAUNCH_OK` |
| `../launch-cloud-extra-high.sh "prompt" [name]` | Same, Director-footer positional form |
| `spawn-waiter.sh --id bc-…` | Register ledger + detached `wait-notify` (auto after launch) |
| `list.sh` / `list-cloud-agents.sh [limit=20]` | Newest agents; each row prints `status=`, `runStatus=`, and `model=` |
| `running-count.sh [--limit N]` | Count `runStatus=RUNNING` for `GCS_CLOUD_REPO`; `CLOUD_MUST_LAUNCH` if below 8 |
| `status.sh` / `status-cloud-agent.sh <bc-id>` | Compact agent + latest-run status |
| `watch.sh` / `watch-cloud-agent.sh <bc-id>` | Poll until terminal; exit 0 on FINISHED |
| `followup.sh` / `followup-cloud-agent.sh <bc-id> "prompt"` | Resume + send a new run |
| `result-cloud-agent.sh <bc-id>` | Result/context JSON |
| `webhook-harness.sh serve \| simulate` | Signed webhook receiver / local POST |

Direct SDK CLI: `scripts/cloud/sdk/run.sh <launch|list|status|watch|followup|result|wait-notify> …`

`_common.sh` loads `auth.sh`, dispatches the SDK CLI, and falls back to REST curl. `auth.sh` is the shared HTTP helper (Basic auth, `CURSOR_API_BASE`, redaction).

## Launch contract

Hard-wired Extra High create **and send** (SDK `Agent.create` + `agent.send` / REST `POST /v1/agents` and `POST /v1/agents/{id}/runs`):

- `model.id = grok-4.6` (not `CURSOR_CLOUD_MODEL` / `CURSOR_CLOUD_EFFORT`)
- `model.params`: `effort=xhigh`, `fast=false`
- SDK first run and follow-up call `sendPinned` → `agent.send(prompt, { model: extraHighModel() })`
- `repos[0].url` from **`GCS_CLOUD_REPO` or `CLOUD_REPO_URL`** (required; fail closed)
- `repos[0].startingRef` from `GCS_CLOUD_REF` / `CLOUD_REPO_REF` / `CURSOR_CLOUD_REF` (default `main`)
- `autoCreatePR = true`

`CLOUD_LAUNCH_OK` is printed **only** on success. REST prints it only on HTTP 200 or 201. Any other status (including other 2xx), curl failure, SDK create/send failure, missing auth, or a create/send response whose exposed model is not `grok-4.6` / `cursor-grok-4.6-xhigh` prints `CLOUD_LAUNCH_ERR` and exits non-zero. Wrong-model creates are not waitered and are not workers.

Set the Cursor dashboard Cloud Agent default to **grok-4.6 extra-high (xhigh)** so Auto cannot pick Sonnet or Gemini. Never launch a Grok Bot CloudAgent.

**v1 metadata:** do not send `Agent.create({ cloud: { metadata } })` by default. API v1 returns `feature_unavailable: "API v1 agent metadata is not enabled."` Metadata is gated behind `CLOUD_SDK_METADATA=1` (default off; key `gcs`). Retryable/unavailable SDK create failures exit **75** so `_common.sh` still REST-falls-back.

## Waiter + orphan shepherd

After `CLOUD_LAUNCH_OK`, launch registers the bc-id on `.a2a-state/<seat>/fleet.jsonl` and spawns `wait-notify.ts` (SDK `run.wait()`, REST poll when `CURSOR_API_BASE` / `CLOUD_FORCE_REST`). On `FINISHED|ERROR|CANCELLED|EXPIRED` the waiter A2A-pings the owning seat (`FLEET_DONE` / `PR_READY`) and marks `notified_by=waiter`.

Disable with `GCS_SPAWN_WAITER=0` or `CLOUD_SPAWN_WAITER=0`.

`scripts/directors/fleet-shepherd.py` is an **orphan-only** safety net: it skips rows with a live `waiter_pid` or `notified_by` in `{waiter, webhook, shepherd}`.

Optional signed webhooks (`scripts/cloud/webhook_receiver.py`) are the other completion path. Waiter remains the fallback when `GCS_WEBHOOK_SECRET` is unset.

## Node >= 22.13

`@cursor/sdk` requires Node **>= 22.13**. Studio hosts may still be Node 20.

`scripts/cloud/sdk/ensure-node.sh` (invoked by `run.sh`):

1. `GCS_NODE` if it is >= 22.13
2. `node` on `PATH` if new enough
3. Cached official binary at `~/.cache/gcs-node/v22.14.0`
4. `fnm` / `nvm` / `volta` if already installed
5. Download official `node-v22.14.0-<plat>-<cpu>.tar.gz` into that cache

Override cache with `GCS_NODE_CACHE` / version with `GCS_NODE_DIST_VER`. First `run.sh` also `npm install`s `@cursor/sdk` under `scripts/cloud/sdk/` (gitignored `node_modules/`).

## REST fallback

REST is used when any of these is true:

- `CLOUD_FORCE_REST=1`
- `GCS_CLOUD_BACKEND=rest`
- SDK bootstrap fail (`sdk/run.sh` exit 75: missing Node >= 22.13 or npm install fail)
- SDK `Agent.create` retryable/unavailable (exit 75), including v1 `feature_unavailable` metadata
- **`CURSOR_API_BASE` is set** (pytest mock and studio-box routing)

Leave `CLOUD_ALLOW_REST_FALLBACK=1` (default) so a missing Node 22 / failed npm install still talks to the API via curl.  
Set `CLOUD_ALLOW_REST_FALLBACK=0` to fail closed if the SDK cannot start.

Optional overrides: `CURSOR_API_BASE`, `CURSOR_AGENT_ENV`.

Fallback may print `CLOUD_SDK_FALLBACK: …` on stderr. Directors should still only call `scripts/*`. Never print keys.

## Director loop

```bash
export GCS_CLOUD_REPO="https://github.com/example/your-repo"
# 1) Launch grunt
scripts/launch-cloud-extra-high.sh "Implement the assigned outcome. Open a PR." "seat-short-name"
# → CLOUD_LAUNCH_OK id=bc-… run=run-… url=…
# waiter pings this seat when the run is terminal — do not block on watch

# 2) Optional status
scripts/cloud/status-cloud-agent.sh bc-…

# 3) On FLEET_DONE / PR_READY
scripts/cloud/result-cloud-agent.sh bc-…

# 4) Follow-up if needed (agent idle)
scripts/cloud/followup-cloud-agent.sh bc-… "Keep the PR; fix the failing check."
```

## Terminal run statuses

`FINISHED` (success) · `ERROR` · `CANCELLED` · `EXPIRED`  
In-flight: `CREATING` · `RUNNING`

`watch.sh` / `watch-cloud-agent.sh` poll the agent's latest run. `FINISHED` exits 0; the other three terminals exit non-zero.

## List rows: agent status vs run status

Cloud agents are durable membership. `GET /v1/agents` `status` stays `ACTIVE` until archive, even after the latest run is terminal. Directors who only look at `ACTIVE` treat leftover FINISHED grunts as spinning workers.

`list.sh` / `list-cloud-agents.sh` print both on each row:

- `status=` agent lifecycle (`ACTIVE` leftover vs `ARCHIVED`)
- `runStatus=` latest run (`RUNNING` vs `FINISHED`, also `CREATING` / `ERROR` / `CANCELLED` / `EXPIRED` / `none`)
- `model=` when the API exposes it on the latest run (`none` otherwise)

REST resolves `latestRunId` via `GET /v1/agents/{id}/runs/{runId}`. SDK uses `Agent.listRuns`. A missing or failed run fetch prints `runStatus=none`.

Live workers are `runStatus=RUNNING`. `scripts/cloud/running-count.sh` counts those for `GCS_CLOUD_REPO`. Cloud mind / directors `cloud_launch` until `>= GCS_CLOUD_MIN_RUNNING` (default **8**) RUNNING per active repo. Leftover `ACTIVE` is not capacity.

Poll interval: `CLOUD_WATCH_INTERVAL` (short-name default 10s). Optional deadline: `CLOUD_WATCH_TIMEOUT_SEC` (0 = none on `watch.sh`). Long-name `watch-cloud-agent.sh` defaults timeout 1800s / poll 30s when those env vars are unset.

## Rules

- Do **not** print API keys.
- Prefer cloud grunts over large local multi-file rewrites.
- List/status/watch/follow-up/result operate on existing agents; create goes through `launch-cloud-extra-high.sh`.
- Do not call the Cloud Agents REST API from Director seats except via these scripts.
- Never force-push the target repo `main`.
