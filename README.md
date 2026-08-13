# Grok Cloud Studio

Public **control plane** for multi-seat Grok Build Directors plus Cursor Cloud **Extra High** coding grunts.

- A2A hub + send/dispatch bus
- ACP persistent seat daemons + inject
- Cursor Cloud Extra High SDK launcher / status / watch / followup / result
- Fleet shepherd safety net (`FLEET_DONE` / `PR_READY`)
- Optional webhook harness + MCP plugins

> Secret-free, game-free reusable studio bus. Configure your own target repo via `GCS_CLOUD_REPO`.

## Quickstart

```bash
git clone https://github.com/atebites-hub/grok-cloud-studio.git
cd grok-cloud-studio
bash ./install.sh
cp -n .env.example .env
# edit .env — set GCS_CLOUD_REPO and CURSOR_API_KEY (or ~/.config/cursor/agent.env)
bash ./doctor.sh
bash scripts/a2a/start-bus.sh
bash scripts/a2a/send.sh studio-ops "ping: hello from quickstart"
```

Dry-run install:

```bash
bash ./install.sh --dry-run
```

## Layout

- `scripts/a2a/` — Hub, send, dispatch, start-bus
- `scripts/directors/` — ACP daemons, inject, fleet-shepherd, footer
- `scripts/cloud/` — Extra High bash entrypoints + TypeScript SDK
- `scripts/webhook/` — Signed receiver + local simulate harness
- `plugins/` — gcs-a2a + gcs-cursor-cloud MCP wrappers
- `docs/` — Architecture, A2A, cloud, plugins
- `prompts/` — Example generic seat prompts

## Security

- **No secrets in git.** Use `.env.example` placeholders only.
- Never commit `.a2a-state/`, `agent.env`, `auth.json`, or `acp.secret`.
- Scripts redact / avoid printing API keys.

## License

MIT — see [LICENSE](./LICENSE).
