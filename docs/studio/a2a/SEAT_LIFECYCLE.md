# Seat lifecycle protocol

```bash
scripts/a2a/seat-lifecycle.sh start|stop|restart|status <seat|--all>
# alias: scripts/directors/lifecycle-seat.sh
```

A2A control messages: `SEAT_UP seat=…` / `SEAT_DOWN seat=…` / `SEAT_RESTART seat=…` / `SEAT_STATUS seat=all`.

Handle: `seat-lifecycle.sh handle-message "SEAT_UP seat=floor"`.

Reuses start/stop/status seat-daemon scripts. Clears stale pid/lock files.
