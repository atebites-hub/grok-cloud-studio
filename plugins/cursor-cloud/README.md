# Grok Cloud Studio — Cursor Cloud plugin

MCP tools wrapping the Extra High control plane:

- `cloud_launch` — `scripts/launch-cloud-extra-high.sh` (grok-4.6 xhigh)
- `cloud_status` — `scripts/cloud/status-cloud-agent.sh` (prints `runStatus`)
- `cloud_result` — `scripts/cloud/result-cloud-agent.sh`

Target git repo is **required** via `GCS_CLOUD_REPO` or `CLOUD_REPO_URL`. Auth is `CURSOR_API_KEY` (env or `~/.config/cursor/agent.env`). Tools never echo the key. Directors keep launching until ≥8 `runStatus=RUNNING` per repo. Leftover `ACTIVE` is not a worker. Never Bot CloudAgent.

## Install

```bash
grok plugin install ./plugins/cursor-cloud --trust
```

Stdio server: `python3 plugins/cursor-cloud/server.py`.
