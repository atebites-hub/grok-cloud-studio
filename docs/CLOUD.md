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

After `CLOUD_LAUNCH_OK`, hive stamps Living Sky `LIV-*` when the prompt or
`--name` carries an identifier (`scripts/directors/liv_evidence_stamp.py`).
Unset `LINEAR_API_KEY` fails closed. Hub receipts never stamp. See
`docs/studio/LINEAR.md`.
