# A2A bus

```bash
scripts/a2a/start-studio-bus.sh                 # hub + dispatch + fleet-shepherd
scripts/a2a/start-studio-bus.sh start --daemons # also ACP daemons (opt-in)
scripts/a2a/send.sh ops "ping: hello"
scripts/a2a/start-studio-bus.sh status
```

`scripts/a2a/start-bus.sh` is a compatibility wrapper for the same commands.

Cards/registry: `docs/a2a/`. Runtime state lives in `.a2a-state/` (gitignored).

Hub default: `http://127.0.0.1:8732` (`GCS_A2A_HUB` / `GCS_A2A_PORT`).
Example seats: `floor`, `ops`, `cloud`, `qa-a`, `qa-b`.
