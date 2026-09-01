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

Create always sends those fields (SDK `Agent.create` and REST `POST /v1/agents`).
There is no `CURSOR_CLOUD_MODEL` / `CURSOR_CLOUD_EFFORT` override. SDK first
`send` and REST/SDK follow-up pass the same pin (`sendPinned`). Do not vendor
Hermes.

Never Grok Bot CloudAgent. Bot seats (`orchestrator` / `donald`) stay
`skipSeats` / `send.sh`. Directors spawn Extra High via
`scripts/launch-cloud-extra-high.sh`.

Studio Linear is Living Sky (`linear.app/livingsky`, team Livingsky / `LIV`).
NEVER Black Swan.
