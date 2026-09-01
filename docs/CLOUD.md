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

Fail-closed (LIV-67): create **and** send/followup always pin grok-4.6 xhigh `fast=false`. `CURSOR_CLOUD_MODEL` / `CURSOR_CLOUD_EFFORT` are ignored. REST list/runs omit model, so an omitted send uses dashboard Auto (Jay saw Opus 5). Never Bot CloudAgent (omitted model = Auto). GCS #41 send-pin is not required once this is on main.
