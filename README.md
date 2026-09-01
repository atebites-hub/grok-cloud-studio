# Grok Cloud Studio

Secret-free control plane for **Grok Build CLI seats** (Directors) plus **Cursor Cloud Extra High** coding grunts.

This repository is the public extract: A2A hub, ACP seat daemons, Extra High SDK wrappers, waiter, orphan fleet-shepherd, MCP plugins, and a signed webhook harness. It is not a game client. Point Extra High at **your** git repo with `GCS_CLOUD_REPO` / `CLOUD_REPO_URL`.

## What you get

| Piece | Path |
|---|---|
| A2A hub / send / leftover dispatch / GROW wake / mind / duplex / bus | `scripts/a2a/`, `scripts/directors/mind.py` |
| ACP seat daemons + pin-session inject (leftover host OS) | `scripts/directors/start-seat-daemon.sh`, `acp_inject.py`, `seat-prompt-acp.sh` |
| Grok Build seat mind (opt-in, `GCS_MIND_SEATS`) | `scripts/directors/mind.py`, `seat-mind-loop.sh`, `docs/studio/MIND.md` |
| Extra High SDK + bash wrappers | `scripts/cloud/sdk/`, `scripts/launch-cloud-extra-high.sh` |
| Waiter (`GET latest runStatus` → A2A ping owner + `REPORT_TO`) | `scripts/cloud/spawn-waiter.sh`, `sdk/wait-notify.ts` |
| Orphan fleet-shepherd | `scripts/directors/fleet-shepherd.py` |
| MCP plugins | `plugins/a2a`, `plugins/cursor-cloud` |
| Webhook harness | `scripts/cloud/webhook_receiver.py`, `webhook-harness.sh` |
| Board | `docs/studio/TASKBOARD.md` (tcarac/taskboard ticket CLI + HTTP `/mcp`) |
| LIV-62 remaining after #47 | `docs/studio/HERMES_REMAINING.md` — pin + stay-up as grok mind. Do not vendor `hermes-agent`. |

Example seats (edit `docs/a2a/registry.json`): `orchestrator` (Grok Bot, ACP-skipped), `floor`, `ops`, `cloud`, plus Palemon-floor first-class `floor-ops`, `studio-ops`, `art`, `content`, `systems`, `qa-a`, `qa-b`, `audio`, `narrative`. Hub: `127.0.0.1:8732`. ACP ports: live Palemon values in the registry. Crash-safe default `GCS_ACP_SEATS=floor,studio-ops` — never auto-spawn the full registry as `grok agent serve`.

## Quick start

```bash
git clone --recurse-submodules https://github.com/atebites-hub/grok-cloud-studio
cd grok-cloud-studio
export GCS_BOT_AGENT_ID='your-grok-bot-agent-id'   # from Grok Bot settings
./install.sh                                       # binds the Bot seat into A2A
./doctor.sh
```

`./install.sh` without `GCS_BOT_AGENT_ID` still bootstraps Python, then **WARN**s. Re-run install or `scripts/a2a/bind-bot-agent.sh` after setting the id. `./doctor.sh` **FAIL**s while `docs/a2a/bot-agents.json` still has an empty or `REPLACE_WITH_YOUR_GROK_BOT_AGENT_ID` agentId. Pure CI clone checks may set `GCS_BOT_BIND_OPTIONAL=1`.

### Palemon studio wipe

Disaster recovery: `./setup.sh` (deploy, including optional Tailscale Serve) and `./cleanup.sh` (teardown). Live DR loop: `./health_check.sh` + `./recover.sh`. Optional boot timer: `scripts/studio/systemd/install-systemd.sh`. See **[docs/studio/WIPE.md](docs/studio/WIPE.md)**. Clone with `--recurse-submodules` (or `git submodule update --init --recursive`) so `vendor/taskboard` is the v0.6.0 source pin.

Recover today's Palemon floor (first-class mind including CCGS audio/narrative leads, taskboard UI/MCP, no `--daemons`) from a clean machine. Copy `studio.env.example` to `$GCS_A2A_STATE/studio.env` (not committed). Host board: `scripts/studio/taskboard/`.

```bash
cp .env.example .env   # fill GCS_CLOUD_REPO + GCS_BOT_AGENT_ID; never commit .env

# Local bus (hub + leftover dispatch + orphan shepherd). bot-bridge is opt-in (GCS_BOT_BRIDGE=1). ACP daemons are opt-in.
scripts/a2a/start-studio-bus.sh start
# scripts/a2a/start-studio-bus.sh start --daemons   # grok agent serve + GROW wake + host ticker
# GCS_MIND_SEATS=floor,ops scripts/a2a/start-studio-bus.sh start   # Grok Build mind (see docs/studio/MIND.md)

scripts/a2a/send.sh orchestrator "hello from ops"
```

Launch Extra High (requires `CURSOR_API_KEY` in the environment or `~/.config/cursor/agent.env`):

```bash
export GCS_CLOUD_REPO="https://github.com/example/your-repo"
scripts/launch-cloud-extra-high.sh "Implement the assigned outcome. Open a PR." "floor-demo"
# or: scripts/launch-cloud-extra-high.sh --name floor-demo --prompt-file /path/to/prompt.txt
# → CLOUD_LAUNCH_OK id=bc-…  — waiter pings the owning seat when the run finishes (context on the A2A ping + result-cloud-agent.sh). Never Bot CloudAgent.
```

## Environment

See `.env.example`. Prefix is **`GCS_*`**. Important:

- `GCS_CLOUD_REPO` / `CLOUD_REPO_URL` — **required** for Extra High create (fail closed)
- `GCS_BOT_AGENT_ID` — Grok Bot orchestrator id (binds into A2A on install)
- `GCS_BOT_SEAT` — default `orchestrator` (`donald` still works; kept in `skipSeats` for back-compat)
- `GCS_BOT_BIND_OPTIONAL=1` — doctor will not FAIL on placeholder agentId (CI clones only)
- `GCS_BOT_BRIDGE=1` — start bot-bridge (default off; Bot seats stay standby). Leftover live `bot-bridge.pid` is not a default start; recover/start keep the same pid only when this is 1.
- `GCS_CLOUD_REF` — default `main`
- `GCS_PROMPT_DIR` — director prompts dir; empty uses `prompts/` or `docs/studio/directors`
- `GCS_SPAWN_WAITER=0` — disable the detached waiter (tests)
- `GCS_WEBHOOK_SECRET` — enable signed webhook receiver
- `CURSOR_API_KEY` — never print; never commit
- Living Sky Linear (`LINEAR_API_KEY` / `GCS_LINEAR_API_KEY`) — LIV-76 close stale + archive Done/Canceled for the 200 cap; **do not delete**. See `docs/studio/LINEAR.md`. Never Black Swan Money.

## Grok Bot orchestrator (A2A)

Bot seats are **not** ACP inject targets. `install.sh` writes `docs/a2a/bot-agents.json` + `registry.json` `skipSeats` when `GCS_BOT_AGENT_ID` is set. Standing Bot routine on the shared box:

```text
Poll `.a2a-state/orchestrator/bot-wake.txt` (latest) and
`.a2a-state/orchestrator/bot-wake.jsonl` (append log). When a new wake
appears, read the task text and act as the studio orchestrator. Reply
with `scripts/a2a/send.sh <director-seat> "…"`. Do not use acp_inject
or grok agent serve for this seat.
```

Bind later without reinstall: `GCS_BOT_AGENT_ID=… scripts/a2a/bind-bot-agent.sh`

ACP serve, leftover inject, and Extra High `--name donald|orchestrator` are refused (never Bot CloudAgent). Extra High stays `grok-4.6` xhigh `fast=false`. Palemon Linear is Living Sky (`LIV`).

## MCP plugins

```bash
grok plugin install ./plugins/a2a --trust
grok plugin install ./plugins/cursor-cloud --trust
```

Tools: `a2a_list_seats`, `a2a_send`, `cloud_launch`, `cloud_status`, `cloud_result`. Details: `docs/PLUGINS.md`.

## Linear (Living Sky, LIV-76)

Studio Linear is Living Sky (`linear.app/livingsky`, team **LIV**). Never Black Swan Money.
The 200-issue cap is handled by closing stale tickets and archiving Done/Canceled
(`scripts/linear_archive_closed.py`). Do not merge GCS #45 purge-delete. Linear MCP
has no archive mutation.

```bash
python3 scripts/linear_archive_closed.py          # dry-run
python3 scripts/linear_archive_closed.py --apply  # close stale, then issueArchive
```

Details: [docs/studio/LINEAR.md](docs/studio/LINEAR.md).

## Tests + secret scan

```bash
.venv/bin/pytest -q
python3 scripts/secret_scan.py
```

GitHub Actions (`.github/workflows/ship-gate.yml`) runs the same two commands on every pull request via `scripts/ci/ship-gate.sh`. The job fails unless pytest prints `N passed` with N≥1 and `secret_scan=clean`. It does not use leftover-green `--override-ini`, and it does not launch Bot CloudAgent. Empty GitHub checks are not merge evidence. MERGEABLE+empty CI is leftover-green theatre. The required check name is **pytest -q and secret_scan**.

Empty GitHub leftover-green (`MERGEABLE` + no checks) is **not** MERGE_REQUEST evidence. QA must see those two commands **pasted** in the Extra High RESULT or PR body. A check named `pytest -q and secret_scan` SUCCESS is not a substitute. Judge: `python3 scripts/cloud/pr_evidence.py judge`. Never squash CONFLICTING leftover PRs.

The secret scan fails closed on credentials, private-key blocks, and product lore that does not belong in this public control plane.

## License

MIT. See `LICENSE`.
