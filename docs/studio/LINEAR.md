# Living Sky Linear (LIV-76)

Studio Linear is **Living Sky** (`https://linear.app/livingsky`, team **LIV**).
**Never Black Swan Money.** Never print or commit `LINEAR_API_KEY`.

Living Sky shares Linear’s free-tier issue cap (**200** in this studio). The
law is: **archive Done/Canceled**, **close stale** open tickets so Linear can
archive them, and **do not delete**.

GCS **#45** (`scripts/linear_purge_closed.py`, GraphQL `issueDelete` with
`permanentlyDelete`) is the **wrong mechanic**. Do not merge it. Do not remint
that purge-delete slice.

Linear MCP (`https://mcp.linear.app/mcp` in `.cursor/mcp.json`) has **no archive mutation**. Hive archive uses GraphQL `issueArchive` in
`scripts/linear_archive_closed.py`. Do not invent an MCP archive tool. Do not
call `issueDelete`.

```bash
# List Done / Canceled archive candidates and stale open LIV tickets.
# Does not mutate.
python3 scripts/linear_archive_closed.py

# Close stale open tickets (Canceled), then archive those plus already
# Done / Canceled / Duplicate Living Sky issues.
python3 scripts/linear_archive_closed.py --apply
```

Auth (never print, never commit): `GCS_LINEAR_API_KEY` or `LINEAR_API_KEY`,
or `LINEAR_API_KEY_FILE`, or `$GCS_A2A_STATE/secrets/linear.api_key`.

The script skips triage / backlog / unstarted that are not stale, skips
started / in-progress Palemon/GCS work, skips already-archived issues, and
skips any non-Living-Sky team even if Done.
