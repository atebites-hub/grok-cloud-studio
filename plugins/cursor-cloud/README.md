# Grok Cloud Studio — Cursor Cloud plugin

MCP tools wrapping the Extra High control plane:

- `cloud_launch` — `scripts/launch-cloud-extra-high.sh`. `--name` REFUSE if a live `runStatus=RUNNING` Extra High already has that name (no twin remint). Leftover `ACTIVE`+`FINISHED` does not block. Never Grok Bot as the grunt runtime.
- `cloud_list` — `scripts/cloud/list_helper.py` (agent `status` plus latest-run `runStatus`; ACTIVE+FINISHED leftovers are not workers)
- `cloud_status` — `scripts/cloud/status-cloud-agent.sh`
- `cloud_result` — `scripts/cloud/result-cloud-agent.sh`

Target git repo is **required** via `GCS_CLOUD_REPO` or `CLOUD_REPO_URL`. Auth is `CURSOR_API_KEY` (env or `~/.config/cursor/agent.env`). Tools never echo the key.

Requires grok `plugin.json` in this folder (not Hermes `plugin.yaml`).
Copied servers honor `GCS_ROOT`. Do not restack `cloud_followup` into
`mind.py`. Extra High only — never a Grok Bot grunt runtime.

## Install

```bash
grok plugin install ./plugins/cursor-cloud --trust
```

Stdio server: `python3 plugins/cursor-cloud/server.py`.
