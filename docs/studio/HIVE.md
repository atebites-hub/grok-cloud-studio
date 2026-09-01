# Hive law — Manning apply-log (LIV-71)

Studio-ops 10-minute beat is not HEALTH_OK unless it applied a Manning
model to an IaC/Palemon change and wrote that apply to the dated log.

This control plane does **not** ship Palemon game code. Extra High grunts
that change Palemon still target `GCS_CLOUD_REPO`. The apply-log only
records the model title plus the ops/IaC change.

## Law

Each 10-minute beat (`GCS_TICKER_SEC` / `GCS_BEAT_SEC`, default 600)
**MUST** append one `APPLY` line to:

```text
studio-archive/log/YYYY-MM-DD.md
```

Default root: `$GCS_STUDIO_ARCHIVE` or `$GCS_A2A_STATE/studio-archive`.

`./health_check.sh` must **not** print `HEALTH_OK` when the current beat
has no apply-log line. Missing apply-log is `HEALTH_DEGRADED` (hub still
up) or stays `HEALTH_DOWN` if the hub is down.

Never paste copyrighted book text. Cite the **model name** (book title)
and the **IaC/Palemon change** only.

## Allowed models (titles only)

| Model | Apply as (our words, not book text) |
|---|---|
| Grokking Simplicity | Keep calculations out of IaC actions this beat |
| Think Distributed Systems | Treat failure, replication, and timeouts as first-class |
| Looks Good to Me | Keep the beat's diff small and reviewable |
| BDD in Action | Observable behavior: HEALTH_OK only with this beat's APPLY |
| Acing the System Design Interview | Isolate capacity, fail closed, do not grow the seat roster |

`scripts/studio/apply_log.py` rotates one title per beat when `--model`
is omitted. Unknown titles are rejected.

## Line format

```text
- APPLY beat=2026-09-01T15:50Z seat=studio-ops model=BDD in Action change=IaC: bus=ok; Palemon: no game code
```

`beat=` is the UTC window floored to 10 minutes. One APPLY per beat
(idempotent). `change=` must include both `IaC` and `Palemon` and stay
under 240 characters.

## Who writes

`scripts/directors/watchdog-studio-ops.sh` appends at the end of every
10-minute studio-ops beat (`python3 scripts/studio/apply_log.py beat`).
Studio-ops mind/SOUL still owns the law if the watchdog is down: do not
claim health without the line.

## Check

```bash
python3 scripts/studio/apply_log.py beat --change 'IaC: …; Palemon: …'
python3 scripts/studio/apply_log.py check
./health_check.sh
```
