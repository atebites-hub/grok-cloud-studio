# Webhook harness

Optional Cursor Cloud `statusChange` → A2A `FLEET_DONE` without `get_agent_run`.

Canonical receiver: `scripts/cloud/webhook_receiver.py` (this `receiver.py` execs it).

Set `GCS_WEBHOOK_SECRET`, run `scripts/cloud/webhook-harness.sh serve` (or `start-studio-bus.sh start`), then `simulate.sh` / `webhook-harness.sh simulate`.

Docs: `scripts/cloud/README.md` and https://cursor.com/docs/cloud-agent/api/webhooks
