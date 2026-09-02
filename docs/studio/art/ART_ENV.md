# Art env (LIV-93) — Higgsfield + Sentry

Living Sky only. **NEVER Black Swan Money.** Never Bot CloudAgent. Never vendor Hermes.

Cloud-env is **LIV-84**. Use the existing `docs/a2a/cards/cloud-env.json` card, the
cloud-env snapshot, and dashboard Secrets. **Do not remint** cloud-env as a new
product. Do not add a repo `.cursor/environment.json`. Do not add `cloud-env` as
a registry seat.

## Two catalogs

**Do not copy GROK_HOME MCP into Cursor CLI.** Two catalogs. Never fake a transfer.

| Runtime | Catalog | Higgsfield | Sentry |
|---|---|---|---|
| Grok Build | seat `GROK_HOME/config.toml` from `grok-home-higgsfield.toml.example` | grok-only | `SENTRY_DSN` / `GCS_SENTRY_DSN` from env |
| Cursor Cloud Extra High / Cursor CLI | repo `.cursor/mcp.json` (Linear HTTP + taskboard only) **plus** LIV-84 cloud-env snapshot / dashboard Secrets | Cursor Agents MCP **login** on the existing snapshot. Do not dump GROK_HOME. Do not add Higgsfield OAuth to `.cursor/mcp.json`. | same env names on snapshot Secrets |

Grok Bot Higgsfield is a different catalog.

## OAuth / mcp_auth

Do **not** thrash OAuth. Do **not** encode an `mcp_auth` retry loop. Cursor Agents
MCP login is enough when generate is needed. One login. No while-True oauth.

## Secrets

Sentry DSN and Higgsfield tokens come from env / cloud-env dashboard Secrets only.
`secret_scan` must fail on literals. See `cloud-env-secrets.example`. Never print
`CURSOR_API_KEY`, Higgsfield tokens, or Sentry DSNs.

Python helper: `scripts/art/sentry_env.py` (`sentry_dsn_from_env`).

## PAL-8 HOLD

Dewcave generate is **PAL-8 HOLD**, blocked on **session**. Do not launch generate.
Do not invent PNG. Unblock only when a live session exists (`session_unblocked`).

Do not merge GCS #26 or #28. Agent Kanban stays gone.
