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

Grok Build minds stamp Living Sky themselves via seat `GROK_HOME/config.toml`
(separate catalog). Do not have Donald DIY Linear. See `docs/studio/MIND.md`
and the BDD example `docs/studio/bdd/liv_minds_stamp_linear.feature`.

## Launch

```bash
scripts/launch-cloud-extra-high.sh "Implement X. Open a PR." "short-name"
scripts/cloud/watch-cloud-agent.sh bc-...
scripts/cloud/result-cloud-agent.sh bc-...
```

Defaults: model `grok-4.6`, `effort=xhigh`, `fast=false`, `autoCreatePR=true`.
