# Cursor Cloud Extra High control plane

**Brand:** Grok Cloud Studio  
**Auth:** `CURSOR_API_KEY` via env or `~/.config/cursor/agent.env` (never print)  
**Canonical:** `@cursor/sdk` in `scripts/cloud/sdk/` (Node **>= 22.13**)  
**REST:** `https://api.cursor.com/v1/agents` curl is **fallback only**  
**Create defaults:** `grok-4.6` + `effort=xhigh` + `fast=false` + `autoCreatePR=true`

## Required target repo

Set one of: `GCS_CLOUD_REPO`, `CLOUD_REPO_URL`, `CURSOR_CLOUD_REPO`.  
Optional ref: `GCS_CLOUD_REF` / `CURSOR_CLOUD_REF` (default `main`).

## Scripts

| Script | Purpose |
|---|---|
| `../launch-cloud-extra-high.sh --name NAME "prompt"` | Create Extra High agent |
| `list.sh` / `list-cloud-agents.sh` | Newest agents |
| `status.sh` / `status-cloud-agent.sh <bc-id>` | Status |
| `watch.sh` / `watch-cloud-agent.sh <bc-id>` | Poll until terminal |
| `followup.sh` / `followup-cloud-agent.sh <bc-id> "prompt"` | Follow-up run |
| `result-cloud-agent.sh <bc-id>` | Result JSON |

Direct SDK CLI: `scripts/cloud/sdk/run.sh <launch|list|status|watch|followup|result> …`

## Node bootstrap

`sdk/ensure-node.sh` prefers `GCS_NODE`, then PATH, then cache `~/.cache/gcs-node/`, then fnm/nvm/volta, then downloads Node 22.

## Rules

- Do **not** print API keys.
- Prefer cloud grunts over large local multi-file rewrites.
- REST fallback: `CLOUD_FORCE_REST=1` or `GCS_CLOUD_BACKEND=rest`.
