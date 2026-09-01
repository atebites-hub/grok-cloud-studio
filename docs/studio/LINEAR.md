# Linear free-tier purge

Living Sky (`linear.app/livingsky`, team **LIV**) shares Linear’s free-tier
issue cap (**200** in this studio). Closed issues and **archived** issues still
count. The only way off the cap is GraphQL **`issueDelete`** with
`permanentlyDelete: true`.

```bash
# List Done / Canceled / Duplicate Living Sky issues. Does not mutate.
python3 scripts/linear_purge_closed.py

# Permanently delete those candidates. Open Palemon/GCS work is skipped.
python3 scripts/linear_purge_closed.py --apply
```

Auth (never print, never commit): `GCS_LINEAR_API_KEY` or `LINEAR_API_KEY`,
or `LINEAR_API_KEY_FILE`, or `$GCS_A2A_STATE/secrets/linear.api_key`.

The script does **not** call `issueArchive`. It never deletes issues whose
workflow type is triage / backlog / unstarted / started, and it never deletes
a non-Living-Sky team.
