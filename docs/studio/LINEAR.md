# Living Sky Linear — minds stamp after TASK (LIV-82 / LIV-43)

Studio Linear is **Living Sky** (`https://linear.app/livingsky`, team
Livingsky / `LIV`). **NEVER Black Swan Money.** Palemon/GCS issues stay in
this workspace only.

Grok Build minds stamp `LIV-*` themselves. Do not have Donald DIY Linear.
`donald` / `orchestrator` are skipSeats and `liv_stamp.py` refuses them
before any GraphQL call.

## After a TASK completes

Minds comment the owning Living Sky issue (default `LIV-82`) with launch or
pytest evidence. Do not `send.sh donald` to stamp.

```bash
python3 scripts/studio/linear/liv_stamp.py after-task \
  --issue LIV-82 \
  --task "$A2A_TASK_ID" \
  --seat floor \
  --evidence "CLOUD_LAUNCH_OK id=bc-…"$'\n'"pytest evidence: tests/test_liv_stamp_after_task.py"
```

Success prints `LIV_STAMP_OK` (no secrets). Failure prints `LIV_STAMP_ERR`
and exits 2.

Create (Living Sky / `LIV` only), label `atebites-hub/grok-cloud-studio` or
the Palemon GitHub-repo label (same org, studio-kit name; constructed at
runtime so the private-game lore scan stays clean):

```bash
python3 scripts/studio/linear/liv_stamp.py create \
  --title "GCS stamp" \
  --description "CLOUD_LAUNCH_OK / pytest evidence" \
  --label atebites-hub/grok-cloud-studio \
  --seat floor
```

## Config (same secret as Linear MCP)

- GraphQL: `https://api.linear.app/graphql`
- Linear MCP (when the catalog is on GROK_HOME / `.cursor/mcp.json`):
  `https://mcp.linear.app/mcp` `save_comment` / `save_issue` with the same
  body from `build_after_task_body()` / `linear_mcp_save_comment_args()`.
- `LINEAR_API_KEY` from the environment, `$GCS_A2A_STATE/linear.env`, or
  `~/.config/linear/api.key`. Never print it. Never commit it.
- Pytest may set `GCS_LINEAR_GRAPHQL_URL` to a localhost mock.

This CLI does not wait on Linear MCP auth. Extra High Linear MCP login is
desktop-only; cloud snapshots need `LINEAR_API_KEY` in Secrets.

## Out of scope

Does not remint PR #64 MCP catalogs. Does not edit `scripts/cloud/list.sh`
or `recover.sh`.
