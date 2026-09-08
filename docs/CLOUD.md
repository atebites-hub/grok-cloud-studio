# Cursor Cloud Extra High

See also `scripts/cloud/README.md`.

Directors **never block-wait** on Cloud. After `CLOUD_LAUNCH_OK`, the SDK waiter
(`scripts/cloud/sdk/wait-notify.ts` / `run.wait`) A2A-pings the owning seat
with waiter/context return. Collect **context** with
`scripts/cloud/result-cloud-agent.sh` (or MCP `cloud_result`).
Never launch a Grok **Bot CloudAgent**; Extra High is the grunt.

## Required env

```bash
export CURSOR_API_KEY=...          # or ~/.config/cursor/agent.env (never printed)
export GCS_CLOUD_REPO=https://github.com/ORG/REPO
export GCS_CLOUD_REF=main          # optional
```

## Linear (Living Sky)

Cursor Cloud Extra High agents **cannot scrape `GROK_HOME`**. They get Linear
via the cloud environment (cloud-env snapshot / dashboard Secrets / process
env):

- Set `LINEAR_API_KEY` on the Cursor Cloud snapshot or Secrets, or snapshot
  it from `$GCS_A2A_STATE/linear.env` / `GCS_LINEAR_KEY_FILE` (`chmod 600`).
  Never print or commit the key.
- Checkout `.cursor/mcp.json` is Linear HTTP (`https://mcp.linear.app/mcp`)
  plus taskboard only — not a copy of the Grok MCP catalog.
- RUNNING specialists `save_comment` on Living Sky issues
  (`linear.app/livingsky`, team Livingsky / `LIV`). **NEVER Black Swan Money.**

Grok Build minds get Linear via seat `GROK_HOME/config.toml` (separate
catalog). See `docs/studio/MIND.md`.

## Art env (LIV-93) — Higgsfield + Sentry

Cloud-env is **LIV-84**. Use the existing snapshot / `docs/a2a/cards/cloud-env.json`
/ dashboard Secrets. **Do not remint** cloud-env. **NEVER Black Swan Money.**

Two catalogs. Extra High **cannot scrape `GROK_HOME`**:

- Grok Build: seat `GROK_HOME` Higgsfield from
  `docs/studio/art/grok-home-higgsfield.toml.example` (grok-only). Do not copy
  that file into `.cursor/mcp.json`.
- Cursor Cloud Extra High / Cursor CLI: checkout `.cursor/mcp.json` (Linear HTTP
  + taskboard only) plus LIV-84 cloud-env snapshot login for Higgsfield. Cursor
  Agents MCP login is enough when generate is needed. Do not mcp_auth loop.
- `SENTRY_DSN` / `GCS_SENTRY_DSN` from snapshot Secrets / process env only.
  `scripts/art/sentry_env.py` reads the env. Never print the DSN.
- PAL-8 Dewcave generate stays HOLD without a session. Do not invent PNG.

Details: `docs/studio/art/ART_ENV.md`.

## Launch

Seat identity (`install_seat_cloud_cli`) puts `cloud_launch`, `cloud_list`,
`cloud_status`, `cloud_followup`, and `cloud_result` on `$GROK_HOME/bin` and
`~/.grok/bin`. Wrappers exec the bash scripts. Do not wrap `watch`. Do not copy
GROK_HOME MCP into checkout `.cursor/mcp.json` (Linear + taskboard only).

```bash
scripts/launch-cloud-extra-high.sh "Implement X. Open a PR." "short-name"
scripts/launch-cloud-extra-high.sh --name short-name --prompt-file /path/to/prompt.txt
# CLOUD_LAUNCH_OK — do not watch. The SDK waiter A2A-pings the owning seat
# and REPORT_TO (default studio-ops). Collect on FLEET_DONE:
scripts/cloud/status-cloud-agent.sh --ids bc-...,bc-...
scripts/cloud/result-cloud-agent.sh bc-...
```

Prompt is exactly one of: command-line text, stdin `-`, or `--prompt-file PATH`.

Directors (`GCS_DIRECTOR_SEAT` set) get `CLOUD_WATCH_REFUSED`
(`reason=director-no-block-wait`) from
`watch.sh` / `watch-cloud-agent.sh` unless `CLOUD_ALLOW_BLOCK_WAIT=1`.

Launch `--name` **REFUSE**s when a live `runStatus=RUNNING` Extra High already has that name (no twin remint). Leftover `ACTIVE`+`FINISHED` does not block. Name-matched Extra High whose latest runStatus cannot be read is fail-closed (no create). Never Bot CloudAgent.

`CLOUD_API_PARKED` fail-closes Extra High create (`CLOUD_LAUNCH_ERR reason=CLOUD_API_PARKED`) when the env is truthy, `$GCS_A2A_STATE/CLOUD_API_PARKED` exists, or a hive-beats marker exists (`$GCS_HIVE_BEATS/CLOUD_API_PARKED`, `$GCS_STUDIO_ARCHIVE/hive-beats/CLOUD_API_PARKED`, or `$GCS_A2A_STATE/hive-beats/CLOUD_API_PARKED`). No `Agent.create` / REST POST. Never recommends a Bot CloudAgent path.

Follow-up **REFUSE**s when the latest `runStatus` is `RUNNING` (do not stack a second run on a live Extra High). Leftover `ACTIVE`+`FINISHED` shells may be followed up. Never Bot CloudAgent.

Palemon Linear is Living Sky (`LIV`), not Black Swan.

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.

## Game vs studio targeting

`result-cloud-agent.sh` / SDK `collect.ts` JSON includes the bound Extra High
`repos[0].url` as `repoUrl` (and the `repos` array) so Directors can tell which
git remote the grunt opened a PR against:

- **Studio** (`grok-cloud-studio`): this control-plane repo. GitHub issues on GCS.
- **Palemon game**: the private game repo via `GCS_CLOUD_REPO`. Palemon Linear is
  **Living Sky** (team key `LIV`), not Black Swan.

Never launch a Grok Bot CloudAgent as the grunt. Specialists are Cursor Cloud
Extra High only (`scripts/launch-cloud-extra-high.sh`). Compact status also
prints `repoUrl`.

Per-invocation `GCS_CLOUD_REPO` wins over a process-global `CURSOR_CLOUD_REPO` and over `agent.env`. Prefix the var on that command only; the launcher does not export it, so the next launch keeps the original default (studio vs Palemon). Specialists are Cursor Cloud Extra High, not a Grok Bot grunt.

Auth (`scripts/cloud/_common.sh` / `auth.sh`) never prints `CURSOR_API_KEY`, including under `bash -x` and when an `agent.env` dump hits a curl/SDK error stream. `cloud_redact_stream` redacts assignment lines (`export CURSOR_API_KEY=…`). `cloud_load_auth` loads **only** the API key from `agent.env` (it does not `source` the file). Do not launch Bot CloudAgent from this path.

## Optional webhook (statusChange)

`FLEET_DONE` can arrive from a signed Cursor Cloud `statusChange` POST instead of waiter `get_agent_run` polling.

See `scripts/cloud/README.md` (Optional Cursor Cloud webhook). Set `GCS_WEBHOOK_SECRET`, run `scripts/a2a/start-studio-bus.sh start` (or `webhook-harness.sh serve`), and point Cursor at:

```
POST /webhooks/cursor-cloud
X-Webhook-Signature: sha256=<hex>
```

Official payload: `id`, `status`, `target.prUrl` — https://cursor.com/docs/cloud-agent/api/webhooks

Waiter remains the fallback when the secret is unset. Extra High create stays v1 grok-4.6 xhigh `fast=false`.

## Followup-first when create cannot verify `main`

`git ls-remote` can see `main` on the Extra High bound repo (`GCS_CLOUD_REPO`) while Cursor Cloud `Agent.create` returns `[validation_error] Failed to verify existence of branch 'main'` (SHA `startingRef` fails the same way). That is Cursor's GitHub App, not a missing branch.

Do **not** retry `launch-cloud-extra-high.sh` create in a loop. Capacity fill: `scripts/cloud/followup-cloud-agent.sh <existing-bc-id> "prompt"` (`CLOUD_FOLLOWUP_OK`). Follow-up **REFUSE**s when that agent's latest `runStatus` is `RUNNING` (do not stack a second live Extra High). Launch prints `FOLLOWUP_FIRST github_sha=…` on this error. Do not vendor Hermes. Model stays grok-4.6 xhigh `fast=false`. Never Bot CloudAgent.

MCP `cloud_list` (`plugins/cursor-cloud`, `scripts/cloud/list_helper.py`) prints latest-run `runStatus` (`RUNNING` vs `FINISHED`) next to agent `status`. Cursor Cloud agents stay `ACTIVE` until archive, so leftover `ACTIVE`+`FINISHED` rows are not live workers. This is independent of bash `list.sh`.

Fail-closed (LIV-67 / LIV-69): create **and** send/followup always pin grok-4.6 xhigh `fast=false`. Any `CURSOR_CLOUD_MODEL` that is not exactly `grok-4.6` is **rejected** (no create, no send). REST list/runs omit model; omitted send uses dashboard Auto (Jay saw Opus 5). Never Bot CloudAgent. Empty GitHub checks are not merge evidence. MERGEABLE+empty CI is leftover-green theatre.

Empty GitHub leftover-green is not MERGE_REQUEST evidence. QA squash requires pasted `.venv/bin/pytest -q` (`N passed`, N≥1) and `python3 scripts/secret_scan.py` (`secret_scan=clean`). Judge: `python3 scripts/cloud/pr_evidence.py judge`. A GitHub check named `pytest -q and secret_scan` SUCCESS is not the paste. Never squash CONFLICTING leftover PRs.

`scripts/cloud/list.sh` / `list-cloud-agents.sh` print agent `status` (membership, often `ACTIVE`) and latest-run `runStatus` (`RUNNING` vs `FINISHED`). Agent `ACTIVE` is not a live worker. Leftover `ACTIVE`+`FINISHED` must not count as live. REST `list.sh --limit` walks `nextCursor` beyond the API **limit=100** page cap (SDK `list.ts` already did). A catalog page error is fail-closed — never a partial list that looks like `running=0`.

`--repo org/name` (or a full `https://github.com/org/name` URL, `.git` suffix, or SSH form) keeps one bound git remote so Directors can count live `runStatus=RUNNING` per bound repo. List items omit `repos`; the filter loads `GET /v1/agents/{id}` (fallback: run `git.branches[].repoUrl`). Unbound agents are dropped when `--repo` is set. Palemon Linear is Living Sky (`LIV`), not Black Swan.

```bash
scripts/cloud/list-cloud-agents.sh --repo org/name
scripts/cloud/list.sh --repo https://github.com/ORG/REPO
```

Wait-notify (`scripts/cloud/sdk/wait-notify.ts`) GETs `GET /v1/agents/{id}/runs` and A2A-pings `FLEET_DONE` only when the **latest** run is terminal, including waiter/context return from `result`. Leftover `FINISHED` while a newer run is `CREATING`/`RUNNING` is not done. Distinct from occupancy listRuns counts and paginated agent catalog. Never Bot CloudAgent.

Occupancy catalog (`scripts/cloud/occupancy-count.sh`) paginates `Agent.list` / REST `GET /v1/agents` via `nextCursor` beyond the API **limit=100** page cap (hive dump was **439**). `count-running` / occupancy-count **fail-closed** if a page errors — never fake `running=0` from a partial catalog. Existence ACTIVE is not liveness. Palemon Linear is Living Sky (`LIV`).

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

`status.sh` / `status-cloud-agent.sh` take multiple bc-ids or `--ids a,b,c` and print **`runStatus`** on the same line as `id=` (latest run, not leftover agent `ACTIVE`). Compact line includes bound `repoUrl`. Fetches run in parallel so capacity beats do not serial-timeout `get_agent_run`. Does not remint `list.sh` (runStatus already on main). Never Bot CloudAgent.

Fleet floor check (distinct from occupancy catalog #125/#132/#154):
`scripts/cloud/running-count.sh` prints list `runStatus` rows then
`CLOUD_RUNNING` / `CLOUD_MUST_LAUNCH`. Directors must `cloud_launch` until
the target repo has **≥8** in-flight runs (`GCS_CLOUD_MIN_RUNNING`, default 8).
