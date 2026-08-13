# A2A bus

```bash
scripts/a2a/start-bus.sh          # hub + dispatch + optional ACP daemons + fleet-shepherd
scripts/a2a/send.sh studio-ops "ping: hello"
scripts/a2a/start-bus.sh status
```

Cards/registry: `docs/a2a/`. Runtime state lives in `.a2a-state/` (gitignored).

Hub default: `http://127.0.0.1:8732` (`GCS_A2A_HUB` / `GCS_A2A_PORT`).
