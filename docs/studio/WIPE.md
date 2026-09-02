# Palemon studio wipe

Recover today's Palemon floor from a **clean machine** using only this
repository plus BYO secrets (grok login, `CURSOR_API_KEY`, optional Tailscale
already-joined). Do not reconnect Agent Kanban. Do not print keys.

This page lives at **`docs/studio/WIPE.md`** (`$GCS_ROOT/docs/studio/WIPE.md`).
It is not `docs/WIPE.md` and not a repo-root `WIPE.md`. AGENTS.md, README,
`./doctor.sh`, and the DR scripts all point here.

Generic extract start (hub + dispatch only, empty `GCS_MIND_SEATS`) is still
the README quick start. This page is the Palemon-floor path.

## Disaster recovery entrypoints

One-command deploy and teardown:

```bash
./setup.sh           # idempotent: env, install, board, bus (NO --daemons), optional Tailscale Serve, doctor, health_check
./cleanup.sh         # soft: stop Tailscale Serve + bus + board processes only
./health_check.sh    # LIVE probes; HEALTH_OK / HEALTH_DEGRADED / HEALTH_DOWN (exit 0/1/2)
./recover.sh         # restart only what is down (incl. Tailscale Serve if wanted); print RECOVER_OK; re-run health_check
bash scripts/studio/systemd/install-systemd.sh   # optional boot timer -> recover.sh (NO --daemons)
```

`setup.sh` / `cleanup.sh` are the deploy/teardown entrypoints.
`health_check.sh` + `recover.sh` are the **DR loop** once the box is supposed
to be up: probe live hub `/health`, taskboard `:3010`, mcp-http `:3011`, and
each `GCS_MIND_SEATS` mind pid; restart only the down pieces via
`start-studio-bus.sh start` (NO `--daemons`), `start-taskboard.sh start`,
`mcp-http.sh start`, and `start-tailscale-serve.sh start` when Tailscale is
on PATH and `PALEMON_TAILSCALE_SERVE` is not `0`. Do not remint sessions.
Do not wipe state. Do not launch Cursor Cloud. bot-bridge stays off unless
`GCS_BOT_BRIDGE=1`. Do not `systemctl` leftover Agent Kanban units.
Tailscale missing is WARN, not FAIL.

Optional boot hook (user systemd, not grok serve):
`scripts/studio/systemd/install-systemd.sh` renders `gcs-recover.service` +
`gcs-recover.timer` that run `./recover.sh` (`OnBootSec=30`). Skip with
`GCS_SYSTEMD=0`. Dry-run with `GCS_SYSTEMD_DRY_RUN=1`. That path never
passes `--daemons` and never reconnects Agent Kanban.

Default cleanup does not delete `studio.env`, `.env`, grok login, Cursor
login, inboxes, or pins. `CLEANUP_WIPE_STATE=1 ./cleanup.sh` also stops
daemons, then wipes inboxes, mind pins, and `taskboard.db` (warning printed).
`studio.env` is kept. `recover.sh` never deletes `studio.env`.

## Recovered-studio layout (live box)

Do **not** hard-require these absolute paths in scripts. They are the layout
on the recovered studio box:

```text
GCS_ROOT=/workspace/palemon-floor-main          # deploy / code tree
GCS_A2A_STATE=/workspace/palemon/.a2a-state     # live state; never the deploy-tree .a2a-state
```

A wipe clone of grok-cloud-studio can keep `GCS_ROOT` as the checkout and set
`GCS_A2A_STATE` to a sibling state dir. Copy `studio.env.example` there.

## Two-runtime mind law

Mind is mind/IaC, not another ACP wrapper. One mailbox: `inbox.jsonl` +
`mind/offset` + pin (`mind/session` grok UUID, `mind/cursor-session` Cursor
chat id). Grok runner and Cursor CLI runner **share** that mailbox. Offset
advances only on runner exit 0. Huge inboxes rotate the consumed prefix
(`GCS_INBOX_MAX_BYTES`); unread lines stay. `wake.offset` / `mind/offset`
stay consistent.

**Do not copy GROK_HOME MCP into Cursor CLI.** Two catalogs. Never fake a transfer.

- Grok catalog: seat `GROK_HOME/config.toml` (taskboard stdio
  `taskboard --db $GCS_TASKBOARD_DB mcp` plus Linear HTTP
  `https://mcp.linear.app/mcp`) plus `grok plugin install --trust`
  of `plugins/studio-mind`. Studio Linear is Living Sky
  (`linear.app/livingsky`, team Livingsky / `LIV`). NEVER Black Swan Money.
  Grok-home Higgsfield is grok-only, for when grok usage is back.
- Cursor CLI catalog: repo `.cursor/mcp.json` wrapping
  `scripts/studio/taskboard/run-mcp.sh` (same `taskboard --db $DB mcp`, no
  `GROK_HOME`) and Linear HTTP (`Bearer ${LINEAR_API_KEY}`). Linear +
  taskboard only. Do not copy the whole Grok catalog. Higgsfield is Cursor
  catalog login when the runner is Cursor CLI (Art generate). Grok Bot
  Higgsfield is a different catalog.

Cursor Cloud Extra High cannot scrape `GROK_HOME`. Snapshot env
`LINEAR_API_KEY` from the cloud-env / dashboard Secrets so those agents
see Linear via `.cursor/mcp.json`.

Shared tools on PATH only: `ticket` / `tb`, `scripts/a2a/send.sh`,
`scripts/launch-cloud-extra-high.sh`.

No third Python tool loop. No ACP `session/prompt` GROW. No `deliver_wake`
overlay.

The grunt is **Cursor Cloud** (not "Extra High" as the noun, not "Cursor Cloud API").
Effort **grok-4.6 xhigh**, `fast=false`. Grok mind CLI:
`--model grok-4.6 --reasoning-effort xhigh` (extra-high). Cursor fallback:
`--model cursor-grok-4.6-xhigh` only. The PATH launcher stays
`scripts/launch-cloud-extra-high.sh`. Full mind law: `docs/studio/MIND.md`.

## Steps

1. Clone this repo. Python 3.11+.

   ```bash
   git clone --recurse-submodules https://github.com/atebites-hub/grok-cloud-studio
   cd grok-cloud-studio
   # If you already cloned without submodules:
   git submodule update --init --recursive
   ./install.sh          # Python venv + chmod; bind Bot if GCS_BOT_AGENT_ID is set
   cp .env.example .env  # fill GCS_CLOUD_REPO + GCS_BOT_AGENT_ID; never commit .env
   ```

   Board source pin: `vendor/taskboard` (tcarac/taskboard **v0.6.0**, not floating
   main). `./setup.sh` inits the submodule if missing. Do not vendor a compiled
   binary blob.

2. Live knobs live in **`$GCS_A2A_STATE/studio.env`**, not in git.

   ```bash
   mkdir -p "${GCS_A2A_STATE:-.a2a-state}"
   cp studio.env.example "${GCS_A2A_STATE:-.a2a-state}/studio.env"
   # Edit recovered GCS_ROOT / GCS_A2A_STATE paths if this is that box.
   ```

   `start-studio-bus.sh` sources `$GCS_A2A_STATE/studio.env`. Do not commit
   `studio.env`.

3. Install grok CLI and log in (BYO). Never commit `~/.grok/auth.json`.

4. Install Cursor Agent CLI so `agent` is on PATH:

   ```bash
   curl https://cursor.com/install -fsS | bash
   ```

   Optional wrapper (mind Cursor 402 fallback looks for `cursor-grok` first):

   ```bash
   mkdir -p "$HOME/.local/bin"
   ln -sf "$PWD/scripts/host/cursor-grok" "$HOME/.local/bin/cursor-grok"
   ```

   `scripts/host/cursor-grok` prepends `$HOME/.local/bin`, sources
   `$HOME/.config/cursor/agent.env`, then `exec agent --model cursor-grok-4.6-xhigh`.

5. Set `CURSOR_API_KEY` in the environment or `~/.config/cursor/agent.env`.
   Never print it. Never commit it.

   Studio Linear is **Living Sky** (`https://linear.app/livingsky`, team
   Livingsky / `LIV`). **NEVER Black Swan Money.** Cursor Cloud Extra High
   agents cannot scrape `GROK_HOME`: put `LINEAR_API_KEY` in the cloud-env
   snapshot or dashboard Secrets so `.cursor/mcp.json` Linear works.

6. Board + MCP HTTP (tcarac/taskboard v0.6.0; do not compile; do not vendor a
   binary). Source pin is `vendor/taskboard`. One-command board path:

   ```bash
   bash scripts/studio/taskboard/setup-taskboard.sh start   # ticket/tb + UI :3010 + MCP :3011
   bash scripts/studio/taskboard/setup-taskboard.sh status
   ```

   Leaf steps (also used by `./recover.sh` when a port is down):
   `install-taskboard.sh` prefers a
   prebuilt in that checkout; brew tap or the matching v0.6.0 GitHub tarball
   remains the fallback when the submodule has no prebuilt.

   ```bash
   bash scripts/studio/taskboard/install-taskboard.sh
   bash scripts/studio/taskboard/start-taskboard.sh start   # UI 127.0.0.1:3010
   bash scripts/studio/taskboard/mcp-http.sh start          # MCP 127.0.0.1:3011
   # or one-shot: bash scripts/studio/taskboard/maintainer.sh start
   bash scripts/studio/taskboard/health-taskboard.sh       # board-only; GET /health is not enough
   bash scripts/studio/taskboard/maintainer.sh docs
   ```

   `health-taskboard.sh` is the host maintainer probe (DB + UI + ticket list
   or POST `/mcp`). It is not `./health_check.sh` (studio DR) and not
   fleet-shepherd (GCS #112). Seat stdio MCP is GCS #100. Agent Kanban stays
   gone. Studio Linear is Living Sky; NEVER Black Swan Money.

   Host PATH tools after setup: `ticket` / `tb` (wrappers under
   `scripts/studio/taskboard/ticket` and `tb`, linked into `$GCS_ROOT/bin`
   and `~/.local/bin`). Always `--db $GCS_TASKBOARD_DB`. Not a `GROK_HOME`
   copy.

   Board-only wipe (inboxes and mind pins stay; `studio.env` stays):

   ```bash
   GCS_TASKBOARD_WIPE=1 bash scripts/studio/taskboard/setup-taskboard.sh wipe
   ```

   That runs `taskboard --db $DB clear -f` then removes the sqlite file.
   `CLEANUP_WIPE_STATE=1 ./cleanup.sh` calls the same wipe, then also
   deletes inboxes and pins. Living Sky Linear is LIV (`linear.app/livingsky`).
   NEVER Black Swan.

   DB is `$GCS_A2A_STATE/taskboard/taskboard.db` (`PALEMON_A2A_STATE` alias
   accepted). Details: `scripts/studio/taskboard/README.md`.

   studio-ops maintainer (do not remint v0.6.0 unless applying a newer
   `vX.Y.Z`): `bash scripts/studio/taskboard/upgrade-taskboard.sh --check`.
   Bump: `upgrade-taskboard.sh --apply vX.Y.Z` then `install-taskboard.sh`.
   Ticket move uses Crockford ULID. Do not reconnect Agent Kanban. Dashboard
   stays LEGACY.
   Cursor CLI sees the board via checkout `.cursor/mcp.json` (wrapper
   `scripts/studio/taskboard/run-mcp.sh`) plus Linear HTTP. Linear +
   taskboard only. Do not copy `GROK_HOME` MCP.
   Do not put MagicDNS hostnames or private GitHub URLs in that file.

7. Mind seats come from `studio.env` (`GCS_MIND_SEATS` first-class directors
   plus CCGS leads `audio` and `narrative`; not 49 specialists). Start the bus
   **without** `--daemons`:

   ```bash
   scripts/a2a/start-studio-bus.sh start
   ```

   That is hub + leftover dispatch + shepherd + **mind loops**.
   **bot-bridge stays off** unless `GCS_BOT_BRIDGE=1` (Bot seats standby).
   Leftover live `bot-bridge.pid` is not a default start; recover/start
   evict it unless opted in (`ALREADY` only when `GCS_BOT_BRIDGE=1`).
   Bot is not a Cursor CloudAgent.
   It does **not** spawn `grok agent serve` per seat. Never auto-spawn a
   13-seat grok serve floor on a ~15GB box.

8. Tailscale Serve is part of `./setup.sh` (after the bus) when the node is
   **already joined**. Manual fallback:

   ```bash
   bash scripts/studio/taskboard/start-tailscale-serve.sh start
   ```

   Serves `/` → `:3010` and `/mcp` → `:3011`. Funnel off. Host default
   `palemon-studio.panther-arctic.ts.net`. Skip with `PALEMON_TAILSCALE_SERVE=0`
   or if `tailscale` is missing. Never write Tailscale auth key values.
   `./recover.sh` re-applies Serve when the binary is on PATH and the skip
   flag is unset. `./cleanup.sh` stops Serve.

9. Higgsfield: Cursor catalog login when the runner is Cursor CLI (Art
   generate). Grok Bot Higgsfield is a different catalog. Grok-home
   Higgsfield is grok-only, for when grok usage is back. Do not encode
   OAuth secrets. Do not fake a transfer between catalogs. Required env
   names live in `studio.env.example` (`HIGGSFIELD_API_KEY`,
   `HIGGSFIELD_SECRET`, `SENTRY_DSN`, `GCS_SENTRY_DSN`) — never print
   values, never commit them. `./doctor.sh` and `./recover.sh` fail-closed
   if art MCP would leak keys (argv / literal env). LIV-84 Extra High
   Higgsfield is the existing cloud-env snapshot login (do not remint).
   Sentry DSN from dashboard Secrets / env only — not MCP. They also
   fail-closed if the Cursor catalog is merged (Higgsfield or Sentry in
   `.cursor/mcp.json`, even with `${...}` expansions) or cloud-env is
   reminted. Ship gate remains pytest -q + secret_scan.

10. Grok Build HTTP 402: `mind.py` **switches** the persisted runner
    (`$GCS_A2A_STATE/<seat>/mind/runner`) and retries that same mail line
    once on Cursor CLI (`cursor-grok` or `agent --model cursor-grok-4.6-xhigh`).
    Default `GCS_MIND_RUNNER=auto`. Forced `grok`/`cursor` does not flip.
    Not a wipe blocker.

Linear 200-issue cap is **close stale + archive Done/Canceled**, never
purge-delete. See `docs/studio/LINEAR.md`. Do not merge GCS #45.

## Check

```bash
./doctor.sh
./health_check.sh
.venv/bin/pytest -q
python3 scripts/secret_scan.py
```

`./doctor.sh` **WARN**s (does not FAIL) if `grok`, `agent`/`cursor-grok`, or
`taskboard` is missing. It **FAIL**s if `scripts/studio/agent-kanban` reappears
or if `PALEMON_AK_BRIDGE` is set to anything other than `0`/empty,
or if Higgsfield/Sentry art MCP would leak keys (`scripts/studio/higgsfield_sentry.py`)
or if the LIV-84 Extra High Cursor catalog is merged (Higgsfield/Sentry MCP)
or cloud-env is reminted (`scripts/studio/liv84_art_env.py`). `./recover.sh`
fails closed before restarts. Do not remint LIV-84.
`start-studio-bus.sh start` and `./recover.sh` refuse the same reconnect
temptation (`AK_REFUSE`) and never exec leftover `ak` / AMA. Board stays
tcarac/taskboard.

## Seats (first-class)

`floor` (8740), `floor-ops` (8753), `studio-ops` (8752), `art` (8746),
`content` (8742), `systems` (8744), `qa-a` (8748), `qa-b` (8751),
`audio` (8754), `narrative` (8755).
`skipSeats`: `orchestrator`, `donald`. Generic extract still ships `ops` and
`cloud`. ACP/GROW cap stays crash-safe (`GCS_ACP_SEATS` default
`floor,studio-ops` unless `studio.env` overlays the Palemon list).

CCGS lead map (aliases in `scripts/a2a/lib.py`): producer=`floor-ops`,
creative=`floor`, technical=`systems`, game-designer=`content`,
lead-programmer=`systems` until split, art-director=`art`, qa-lead=`qa-a`,
release-manager=`studio-ops`, audio-director=`audio`, audio-lead=`audio`,
narrative-director=`narrative`, narrative-lead=`narrative`. First-class
`audio` and `narrative` stay themselves (registry seats, not aliases).
Unmapped specialist titles do not mint seats. Directors and leads spawn
specialists only via `scripts/launch-cloud-extra-high.sh`. Do not add 49
specialists.
