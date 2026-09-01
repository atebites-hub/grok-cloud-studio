# Grok Cloud Studio — Cursor Cloud plugin

MCP tools wrapping the Extra High control plane:

- `cloud_launch` — `scripts/launch-cloud-extra-high.sh` (grok-4.6, xhigh, `fast=false`)
- `cloud_list` — `scripts/cloud/list-cloud-agents.sh` (runStatus RUNNING vs leftover ACTIVE)
- `cloud_status` — `scripts/cloud/status-cloud-agent.sh`
- `cloud_followup` — `scripts/cloud/followup-cloud-agent.sh`
- `cloud_result` — `scripts/cloud/result-cloud-agent.sh`

Do not wrap `watch` as an MCP tool. Target git repo is **required** via `GCS_CLOUD_REPO` or `CLOUD_REPO_URL`. Auth is `CURSOR_API_KEY` (env or `~/.config/cursor/agent.env`). Tools never echo the key.

## Install

```bash
grok plugin install ./plugins/cursor-cloud --trust
```

Stdio server: `python3 plugins/cursor-cloud/server.py`.
