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

## Game vs studio targeting

`result-cloud-agent.sh` / SDK `collect.ts` JSON includes the bound Extra High
`repos[0].url` as `repoUrl` (and the `repos` array) so Directors can tell which
git remote the grunt opened a PR against:

- **Studio** (`grok-cloud-studio`): this control-plane repo. GitHub issues on GCS.
- **Palemon game**: the private game repo via `GCS_CLOUD_REPO`. Palemon Linear is
  **Living Sky** (team key `LIV`), not Black Swan.

Never launch a Grok Bot CloudAgent as the grunt. Specialists are Cursor Cloud
Extra High only (`scripts/launch-cloud-extra-high.sh`).
