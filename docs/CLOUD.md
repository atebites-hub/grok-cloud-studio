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

## LIV-41 directors-watch (FAIL closed)

Directors spawn **and monitor** their own Extra High bc-ids. After
`CLOUD_LAUNCH_OK`, invoke `cloud_wait` or `scripts/cloud/spawn-waiter.sh --id
<bc-id>` so `wait-notify.ts` A2A-pings the **owning seat** `FLEET_DONE` /
`PR_READY`. Do not block the director turn on `watch-cloud-agent.sh`.
fleet-shepherd is orphan-only, not the monitor. Never Bot CloudAgent
(orchestrator / donald). Do not dump watching to Donald.

A director turn that owns a grunt and does not actually watch it is **FAIL**
(`reason=no-watch`). Demonstrate, don't theatre. Studio Linear is **Living Sky**
(`LIV`), never Black Swan. Extra High stays **grok-4.6**, `effort=xhigh`,
`fast=false`.

Judge: `scripts/directors/director_turn_watch.py`. Feature:
`docs/studio/bdd/liv41_directors_watch.feature`.
