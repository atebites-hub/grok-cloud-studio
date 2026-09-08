# Cursor Cloud Extra High control plane

**Audience:** Grok Cloud Studio Directors (and QA for rebase-only Extra High)  
**Auth:** `CURSOR_API_KEY` via env or `~/.config/cursor/agent.env` (never print, including `bash -x` and agent.env dumps)  
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
| `../launch-cloud-extra-high.sh --name NAME "prompt"` | Create Extra High agent + initial run (PR auto). Prints `CLOUD_LAUNCH_OK`. **REFUSE** if a live `runStatus=RUNNING` agent already has that name (no twin remint). Leftover `ACTIVE`+`FINISHED` does not block. Never Bot CloudAgent. |
| `../launch-cloud-extra-high.sh "prompt" [name]` | Same, Director-footer positional form |
| `../launch-cloud-extra-high.sh --name NAME --prompt-file PATH` | Same, prompt from a file (not stuffed on argv) |
| `../launch-cloud-extra-high.sh --name NAME -` | Same, prompt from stdin |
| `spawn-waiter.sh --id bc-…` | Register ledger + detached `wait-notify` (auto after launch) |
| `list.sh` / `list-cloud-agents.sh [--limit N] [--repo org/name]` | Newest agents; each row prints agent `status` and latest-run `runStatus`. `--repo` keeps one bound git remote so Directors can count `runStatus=RUNNING`. REST walks `nextCursor` when `--limit` exceeds the API page cap (100). Fail-closed if a page errors. |
| `occupancy-count.sh` | Paginated occupancy catalog (`Agent.list` / `GET /v1/agents` via `nextCursor`, page size 100). Prints `CLOUD_OCCUPANCY running= leftover_active= creating= listed= pages=`. Fail-closed `CLOUD_OCCUPANCY_ERR reason=page` if a page errors — never fake `running=0`. |
| `running-count.sh [--limit N]` | In-flight count for `GCS_CLOUD_REPO`; prints `runStatus` rows then `CLOUD_RUNNING` / `CLOUD_MUST_LAUNCH`. Distinct from occupancy catalog. |
| `status.sh` / `status-cloud-agent.sh <bc-id> [<bc-id>…] [--ids id,id]` | Compact **runStatus** + **repoUrl** per id (parallel; not leftover ACTIVE) |
| `watch.sh` / `watch-cloud-agent.sh <bc-id>` | Operator poll until terminal. Directors (`GCS_DIRECTOR_SEAT` set) get `CLOUD_WATCH_REFUSED` (`reason=director-no-block-wait`) unless `CLOUD_ALLOW_BLOCK_WAIT=1` |
| `followup.sh` / `followup-cloud-agent.sh <bc-id> "prompt"` | Resume + send a new run. **REFUSE** if latest `runStatus=RUNNING` (do not stack a second live Extra High). Leftover `ACTIVE`+`FINISHED` may follow up. Never Bot CloudAgent. |
| `result-cloud-agent.sh <bc-id>` | Non-blocking result/context JSON (`repoUrl` = bound `repos[0].url`) |
| `pr_evidence.py judge` | MERGE_REQUEST paste gate: leftover-green empty GitHub checks are not ship-gate; require pasted `pytest -q` (`N passed`) + `secret_scan=clean`. CONFLICTING/DIRTY never squash. Verdict JSON only (never prints tokens). |
| `webhook-harness.sh serve \| simulate` | Signed webhook receiver / local POST |

Direct SDK CLI: `scripts/cloud/sdk/run.sh <launch|list|status|watch|followup|result|wait-notify|occupancy> …`

`_common.sh` loads `auth.sh`, dispatches the SDK CLI, and falls back to REST curl. `auth.sh` is the shared HTTP helper (Basic auth, `CURSOR_API_BASE`, redaction). `cloud_load_auth` keeps `set +x` until after the key presence check so `bash -x` cannot dump `CURSOR_API_KEY`. `cloud_redact_stream` redacts the live key value and `agent.env` assignment dumps (`export CURSOR_API_KEY=…`) even when the env var is unset.

## Launch contract

Hard-wired Extra High create (SDK `Agent.create` / REST `POST /v1/agents`):

- `model.id = grok-4.6` (pinned; Extra High create does not take the Cursor CLI mind model id)
- `model.params`: `effort=xhigh`, `fast=false`
- `repos[0].url` from **`GCS_CLOUD_REPO` or `CLOUD_REPO_URL`** (required; fail closed)
- `repos[0].startingRef` from `GCS_CLOUD_REF` / `CLOUD_REPO_REF` / `CURSOR_CLOUD_REF` (default `main`)
- `autoCreatePR = true`

Collect (`result-cloud-agent.sh` / `collect.ts`) echoes that bound `repos[0].url`
as `repoUrl` so Directors can see **game vs studio** targeting (Palemon vs
`grok-cloud-studio`). Compact status prints `repoUrl`. Palemon Linear is
**Living Sky** (`LIV`), not Black Swan. Never launch a Grok Bot CloudAgent;
Extra High is the grunt.

Prompt sources (exactly one): argv text, stdin `-`, or `--prompt-file PATH` (readable file; empty/whitespace is `CLOUD_LAUNCH_ERR`). Mixing `--prompt-file` with argv text or stdin `-` is `CLOUD_LAUNCH_ERR`.

Per-invocation `GCS_CLOUD_REPO` / `CLOUD_REPO_URL` wins over a process-global `CURSOR_CLOUD_REPO` and over any `GCS_CLOUD_REPO` in `~/.config/cursor/agent.env` (auth loads **only** the API key from that file; it does not `source` the file). The launcher does not `export` the resolved repo, so the next launch sees the original process environment (studio vs Palemon). Specialists are Cursor Cloud Extra High, not a Grok Bot grunt.

Directors-spawn law (LIV-41): if **playability** work is in progress and
RUNNING Extra High count for `GCS_CLOUD_REPO` is below 8, cloud mind MUST
`scripts/launch-cloud-extra-high.sh`. Do not reuse
`--name gcs-liv41-mind-must-launch`. Never Bot CloudAgent. See `docs/CLOUD.md`.

`CLOUD_LAUNCH_OK` is printed **only** on success. REST prints it only on HTTP 200 or 201. Any other status (including other 2xx), curl failure, SDK create failure, missing auth, or a live `--name` twin (`runStatus=RUNNING`) prints `CLOUD_LAUNCH_ERR` and exits non-zero. Leftover `ACTIVE`+`FINISHED` with the same name does not block. Name-matched Extra High whose latest runStatus cannot be read is fail-closed (no create). Palemon Linear is Living Sky (`LIV`). Never Bot CloudAgent.

If Cursor Cloud returns `Failed to verify existence of branch|commit` while `git ls-remote` resolved the ref, create prints `FOLLOWUP_FIRST` and exits 1 (no REST retry). Fill capacity with `followup-cloud-agent.sh` on an existing Extra High. See `docs/CLOUD.md`.


**v1 metadata:** do not send `Agent.create({ cloud: { metadata } })` by default. API v1 returns `feature_unavailable: "API v1 agent metadata is not enabled."` Metadata is gated behind `CLOUD_SDK_METADATA=1` (default off; key `gcs`). Retryable/unavailable SDK create failures exit **75** so `_common.sh` still REST-falls-back.

## Waiter + orphan shepherd

After `CLOUD_LAUNCH_OK`, launch registers the bc-id on `.a2a-state/<seat>/fleet.jsonl` and spawns `wait-notify.ts` (SDK `listRuns` + `run.wait()`, REST `GET /v1/agents/{id}/runs` when `CURSOR_API_BASE` / `CLOUD_FORCE_REST`). The waiter GETs **latest** `runStatus`. Leftover `FINISHED` while a newer run is `CREATING`/`RUNNING` is not done. On latest `FINISHED|ERROR|CANCELLED|EXPIRED` the waiter A2A-pings the owning seat and `REPORT_TO` (default `studio-ops`) (`FLEET_DONE` / `PR_READY` / `INSPECT`) and marks `notified_by=waiter`. If `prUrl` is a GitHub **draft**, the ping includes `draft=true` and must not be treated as MERGE_REQUEST-ready (QA does not squash drafts). If GitHub `mergeable` is **CONFLICTING** (`mergeable_state=dirty`, e.g. sibling PRs #301/#304), the ping includes `mergeable=CONFLICTING` and QA **HOLD squash** (Extra High rebase only; not MERGE_REQUEST-ready). If the latest run is `CANCELLED` and `prUrl` still exists, the ping is `INSPECT follow-up-or-close` — not `PR_READY` / `MERGE_REQUEST`. If `prUrl` is a GitHub pull with empty checks (`check_runs=0`), the ping is not MERGE_REQUEST-ready — empty GitHub checks are not evidence; MERGEABLE+empty CI is leftover-green theatre. The required check is GitHub Actions **pytest -q and secret_scan**.

`get_agent_run` is capped at 6000/hour. Waiters exponential-backoff on HTTP 429 (`CLOUD_WAITER_RETRY`, `CLOUD_WAITER_BACKOFF_MS` / `CLOUD_WAITER_BACKOFF_CAP_MS`, Retry-After when positive) and resume until the **run** is terminal. Agent `ACTIVE` is durable membership — leftover `ACTIVE`+`FINISHED` is not an in-flight worker.

`spawn-waiter.sh` registers a **supervisor** pid. If `wait-notify` still prints `CLOUD_WAITER_ERR` and exits on a rate-limit, the supervisor restarts it (`CLOUD_WAITER_RESTART`) so fleet-shepherd does not treat a 429 death as an orphan. Tests may set `CLOUD_WAITER_BIN`.

Disable with `GCS_SPAWN_WAITER=0` or `CLOUD_SPAWN_WAITER=0`.

`scripts/directors/fleet-shepherd.py` is an **orphan-only** safety net: it skips rows with a live `waiter_pid` or `notified_by` in `{waiter, webhook, shepherd}`. Presence of `waiter_pid` is **not** liveness. A pid that names a dead process is evicted durably on `fleet.jsonl` (`waiter_pid` null, `waiter_tombstone`) so a reused pid cannot look live; shepherd then orphan-notifies **once**. Distinct from leftover `ACTIVE`+`FINISHED` skip and from `bot-bridge.pid` tombstones. It also skips leftover shells so it does not `get_agent_run` them: notified closed rows, and agents whose latest run is already `FINISHED`. Cursor Cloud agent `status` stays `ACTIVE` until archive; probing those leftovers burns the hourly run-GET cap and looks like spinning workers. Each cycle also probes tcarac/taskboard health (DB file + `ticket list` or HTTP `/mcp`) and logs `TASKBOARD_HEALTH_OK` or `TASKBOARD_HEALTH_FAIL`. GET `/health` is not the probe. Taskboard health is not leftover-shell skip and does not install seat stdio MCP. `fleet_ledger.notify_owner` is idempotent: a second notify on a row already `notified_by=waiter` does not A2A-ping again (waiter+shepherd must not double-fire `FLEET_DONE`).

`python3 scripts/cloud/fleet_ledger.py prune` drops leftover `.a2a-state/<seat>/fleet.jsonl` rows that are already closed (`notified`, `status=closed`, latest run `FINISHED|ERROR|CANCELLED|EXPIRED`). Open leftover shells stay on the ledger. Prune is ledger-only: it does not probe Cursor Cloud or A2A-ping. `--dry-run` reports without rewriting; `--seat` limits to one seat.

## Optional Cursor Cloud webhook (statusChange)

`FLEET_DONE` does not have to wait on waiter `get_agent_run` polling. Cursor Cloud documents a signed `statusChange` webhook for `FINISHED` / `ERROR`:

https://cursor.com/docs/cloud-agent/api/webhooks

Point that hook (Cursor dashboard Cloud Agent webhooks, or v0 create `webhook.url`) at this studio:

```
POST http://127.0.0.1:8788/webhooks/cursor-cloud
```

Also accepted: `POST /v0/statusChange` and `POST /hook`.

Headers (official):

- `X-Webhook-Signature: sha256=<hex>` — HMAC-SHA256 of the **raw** body with `GCS_WEBHOOK_SECRET`
- `X-Webhook-Event: statusChange`
- `User-Agent: Cursor-Agent-Webhook/1.0`

Body (official): `event`, `id` (bc-id), `status`, `target.prUrl`, `target.url`, `summary`.

GCS Extra High create stays **v1** (`POST /v1/agents`, grok-4.6 xhigh `fast=false`) and does **not** attach a v0 `webhook` object (v1 docs have no webhook field). The documented hook is this receiver. Waiter remains the fallback when `GCS_WEBHOOK_SECRET` is unset.

Enable:

```bash
export GCS_WEBHOOK_SECRET='…'   # never print or commit; 32+ chars for Cursor v0
export GCS_WEBHOOK_URL='https://your-tunnel.example/webhooks/cursor-cloud'  # tell Cursor
scripts/a2a/start-studio-bus.sh start   # starts receiver when secret is set
# or: scripts/cloud/webhook-harness.sh serve
scripts/cloud/webhook-harness.sh simulate --id bc-test --status FINISHED --pr URL
```

Do not remint waiter 429 backoff or fleet notify dedupe here. Cursor `statusChange` retries return HTTP 200 `duplicate` without a second A2A ping. Never print the secret.

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
#    --name REFUSE if a live runStatus=RUNNING Extra High already has that name
#    (no twin remint). Leftover ACTIVE+FINISHED does not block.
#    Never Bot CloudAgent (orchestrator/donald is send.sh). Palemon Linear is Living Sky (LIV).
scripts/launch-cloud-extra-high.sh --name seat-short-name --prompt-file /path/to/prompt.txt
# or: scripts/launch-cloud-extra-high.sh "Implement the assigned outcome. Open a PR." "seat-short-name"
# → CLOUD_LAUNCH_OK id=bc-… run=run-… url=…
# waiter pings this seat when the run is terminal — do not block on watch

# 2) Optional status (batch ids — do not serial-timeout 10 get_agent_run calls)
scripts/cloud/status-cloud-agent.sh bc-…
scripts/cloud/status-cloud-agent.sh --ids bc-a,bc-b,bc-c
# → id=bc-a agentStatus=ACTIVE runStatus=RUNNING …

# 3) On FLEET_DONE / PR_READY
scripts/cloud/result-cloud-agent.sh bc-…
# JSON includes repoUrl (bound repos[0].url) plus emptyChecks / shipGateOk / checkRuns
# when prUrl is a GitHub pull. emptyChecks=true is not MERGE_REQUEST evidence.
# emptyChecks=true is not MERGE_REQUEST evidence (MERGEABLE+empty CI is leftover-green theatre).
# HOLD MERGE_REQUEST until the Extra High RESULT / PR body pastes
# .venv/bin/pytest -q (N passed) and python3 scripts/secret_scan.py
# (secret_scan=clean). Empty GitHub leftover-green is not a ship-gate.
# python3 scripts/cloud/pr_evidence.py judge

# 4) Follow-up if the latest run is idle (leftover ACTIVE+FINISHED).
#    REFUSE if runStatus=RUNNING — do not stack a second run on a live Extra High.
#    Never Bot CloudAgent (orchestrator/donald is send.sh).
scripts/cloud/followup-cloud-agent.sh bc-… "Keep the PR; fix the failing check."
```

## List rows: `--repo` and runStatus

Cloud agents stay `ACTIVE` until archive. Execution state lives on the latest
run. Directors count **live** workers with `runStatus=RUNNING` for the bound
repo — leftover `ACTIVE`+`FINISHED` is not capacity.

```bash
scripts/cloud/list-cloud-agents.sh --repo org/name
scripts/cloud/list.sh --repo https://github.com/org/name
```

`--repo` accepts `org/name`, `https://github.com/org/name`, a `.git` suffix, or
`git@github.com:org/name.git`. List items omit `repos`; the filter loads
`GET /v1/agents/{id}` (and the latest run, including `git.branches[].repoUrl`
when the agent record has no repos). Unbound agents are dropped when
`--repo` is set.

Palemon Linear is **Living Sky** (`LIV`), not Black Swan. Never Bot CloudAgent.

## Terminal run statuses

`FINISHED` (success) · `ERROR` · `CANCELLED` · `EXPIRED`  
In-flight: `CREATING` · `RUNNING`

`watch.sh` / `watch-cloud-agent.sh` poll the agent's latest run. **Directors must not call them** (LIV-103): launch already spawned `wait-notify` (`run.wait`) which A2A-pings the owning seat and `REPORT_TO` (default `studio-ops`) with waiter/context return. With `GCS_DIRECTOR_SEAT` set they print `CLOUD_WATCH_REFUSED` (`reason=director-no-block-wait`) and exit 2 unless `CLOUD_ALLOW_BLOCK_WAIT=1`. `FINISHED` exits 0; the other three terminals exit non-zero.

Poll interval: `CLOUD_WATCH_INTERVAL` (short-name default 10s). Optional deadline: `CLOUD_WATCH_TIMEOUT_SEC` (0 = none on `watch.sh`). Long-name `watch-cloud-agent.sh` defaults timeout 1800s / poll 30s when those env vars are unset.

## List rows: agent status vs run status

Cloud agents are durable membership. `GET /v1/agents` `status` stays `ACTIVE` until archive, even after the latest run is terminal. Directors who only look at `ACTIVE` treat leftover FINISHED grunts as spinning workers (stale membership). Existence is not liveness.

`list.sh` / `list-cloud-agents.sh` print both on each row:

- `status=` agent lifecycle (`ACTIVE` leftover vs `ARCHIVED`)
- `runStatus=` latest run (`RUNNING` vs `FINISHED`, also `CREATING` / `ERROR` / `CANCELLED` / `EXPIRED` / `none`)

REST resolves `latestRunId` via `GET /v1/agents/{id}/runs/{runId}` (`scripts/cloud/list_rows.py`). SDK uses `Agent.listRuns`. A missing or failed run fetch prints `runStatus=none`.

Live workers are `runStatus=RUNNING`. Leftover `status=ACTIVE` + `runStatus=FINISHED` is membership, not a spinning worker.

## Occupancy catalog (paginate beyond 100)

`GET /v1/agents` and SDK `Agent.list` cap each page at **100**. A hive dump of **439** Extra Highs is five pages. Capacity beats must walk `nextCursor` until it is omitted (not returned as `null`).

REST `list.sh --limit` uses the same paginator (`list_catalog.py` / `max_items`) so Directors who count `runStatus=RUNNING` from list rows also see workers past page 1. Occupancy-count remains the one-line capacity path.

`scripts/cloud/occupancy-count.sh` is the occupancy path (SDK `occupancy.ts` / REST `occupancy_count.py`). It prints `CLOUD_OCCUPANCY running=N leftover_active=N creating=N listed=N pages=N`. If any catalog page errors, it prints `CLOUD_OCCUPANCY_ERR reason=page` and exits non-zero — **never** a fake `running=0` from a partial list. Skip `GCS_BOT_AGENT_ID`. Distinct from leftover occupancy GCS #132 (do not rebase).

## Fleet floor (running-count)

Directors must `cloud_launch` until ≥8 in-flight runs per `GCS_CLOUD_REPO`
(`GCS_CLOUD_MIN_RUNNING`, default 8). Count `runStatus` (`RUNNING`/`CREATING`),
not leftover `ACTIVE`+`FINISHED`. `list.sh` and batch `status.sh` already print
`runStatus`. Check the floor with `scripts/cloud/running-count.sh`
(`CLOUD_MUST_LAUNCH`). Never Bot CloudAgent.
This is not occupancy remint (#125 / #132 / #154).

## Rules

- Do **not** print API keys.
- Prefer cloud grunts over large local multi-file rewrites.
- List/status/watch/follow-up/result operate on existing agents; create goes through `launch-cloud-extra-high.sh`.
- Do not call the Cloud Agents REST API from Director seats except via these scripts.
- Never force-push the target repo `main`.
