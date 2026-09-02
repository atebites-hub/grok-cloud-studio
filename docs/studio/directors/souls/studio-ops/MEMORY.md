# Memory — studio-ops

Bus and daemon notes live here across turns. First-class seat; not only an ops alias.

Board host kit: `scripts/studio/taskboard/maintainer.sh` (start/stop/status/health/docs) and `health-taskboard.sh`. Pin file: `scripts/studio/taskboard/PIN` (v0.6.0). Check with `upgrade-taskboard.sh --check`. Ticket move is ULID. Do not reconnect Agent Kanban.

Wipe-box board: `scripts/studio/taskboard/setup-taskboard.sh start|stop|wipe`. Host PATH is `ticket` / `tb` against `$GCS_TASKBOARD_DB`. Living Sky Linear is LIV.
