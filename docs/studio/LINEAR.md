# Hive Linear (Living Sky)

After each **successful mind turn**, the hive (Python mailbox + pin + stay-up in
`scripts/directors/mind.py` / `linear_hive.py`) comments the matching Living Sky
Linear issue. Grok Bot does not write Linear. Donald is notified via **A2A only**.

## Law

- Hive stamps Linear autonomously after `MIND_TURN` (runner exit 0, offset advanced).
- Extract identifiers like `LIV-82` from mail + turn text (default team key `LIV`).
- Comment body is redacted. Never print `LINEAR_API_KEY`.
- Then `scripts/a2a/send.sh --from <seat> donald "LINEAR_STAMP … source=hive-mind"`.
- **Do not stamp Linear from Grok Bot.** Bot standing routines must not call
  `api.linear.app`. `LINEAR_STAMP` / `LINEAR_SKIP` / `LINEAR_FAIL` on Donald's
  inbox are receipts, not a prompt to write Linear.
- Missing key, disable flag, or GraphQL errors do **not** roll back the mind
  offset. Fail-open for the turn; log `LINEAR_SKIP` / `LINEAR_FAIL`.
- No issue id (keep-alives, STATUS/CONTINUE) → `LINEAR_SKIP reason=no-issue` and
  **no** Donald ping (avoid noise).
- Empty CI is not merge. Ship gate is `.venv/bin/pytest -q` and
  `python3 scripts/secret_scan.py` on GitHub Actions.

## Env

Copy into `.env` / `$GCS_A2A_STATE/studio.env`. Never commit values.

| Knob | Role |
|---|---|
| `LINEAR_API_KEY` | Linear personal/API key (required to stamp) |
| `GCS_LINEAR_A2A_SEAT` | Default `donald` |
| `GCS_LINEAR_TEAM_KEYS` | Default `LIV` (comma list) |
| `GCS_LINEAR_DISABLE` | `1` skips GraphQL; still A2A `LINEAR_SKIP reason=disabled` when ids exist |
| `GCS_LINEAR_API` | Default `https://api.linear.app/graphql` |
| `GCS_LINEAR_TIMEOUT` | Seconds (default 10) |
| `GCS_LINEAR_MAX_ISSUES` | Cap per turn (default 5) |

Receipts: `$GCS_A2A_STATE/<seat>/mind/linear.jsonl` (no secrets).

## Not a grok tool

`plugins/studio-mind` stays `ticket`, `a2a_send`, `cloud_launch`. Linear is not
an agent plugin. Python runs it after the turn. Bot-bridge does not import it.
