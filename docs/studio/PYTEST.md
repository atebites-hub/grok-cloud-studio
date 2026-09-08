# Isolated pytest (live Palemon bus)

Directors on the recovered studio box export `GCS_ACP_SEATS`,
`GCS_MIND_SEATS`, `GCS_A2A_STATE`, `GCS_A2A_REGISTRY`, and
`GCS_TASKBOARD_DB`. The live A2A hub holds `127.0.0.1:8732` and the host
taskboard SQLite lives under `$GCS_A2A_STATE/taskboard/taskboard.db`
(recovered layout: `/workspace/palemon/.a2a-state`). Leaking those knobs
into `.venv/bin/pytest -q` opens the real Palemon hub and board.

This page is the isolation contract. It is not a one-line comment in
`pytest.ini`. Living Sky only. Never Bot CloudAgent. Never vendor Hermes.
Do not start the live bus from tests. Do not bounce leftover dispatch.

## Required wiring

| Piece | Role |
|---|---|
| `scripts/gcs_pytest_isolate.py` | Plugin + helpers. `--check` is the doctor/ship-gate contract. |
| `tests/conftest.py` | `pytest_plugins = ("gcs_pytest_isolate",)` so `tests/` always loads it. |
| `pytest.ini` | `pythonpath = scripts` and `addopts = -p gcs_pytest_isolate`. **Do not add `-q`.** |
| `scripts/ci/ship-gate.sh` | `unset`s the leak variables (and `PALEMON_A2A_STATE` / `TASKBOARD_DB` aliases) **before** `.venv/bin/pytest -q`. |
| `./doctor.sh` | Fails closed if `--check` finds missing plugin, conftest, pytest.ini `-p`, ship-gate unset, or this page. |

A file-level `pytest tests/foo.py` still loads the plugin via `addopts = -p`.
Dropping that `-p` line fails doctor and the isolation FAT.

## What the plugin does

1. **Strip** `GCS_ACP_SEATS`, `GCS_MIND_SEATS`, `GCS_A2A_STATE`,
   `GCS_A2A_REGISTRY`, `GCS_TASKBOARD_DB` from `os.environ` during
   `pytest_configure` (plus aliases `PALEMON_A2A_STATE` and `TASKBOARD_DB`,
   which still resolve the live board).
2. **Opt-in temp state:** request fixture `gcs_temp_state`. It points
   `GCS_A2A_STATE` and `GCS_TASKBOARD_DB` at `tmp_path / "a2a-state"` for
   that test only. ACP/MIND/registry stay unset unless the test sets them.
3. **Refuse live hub port:** `socket.bind` of `*:8732` raises
   `LiveHubBindError`. Hub/`start-studio-bus.sh start` with
   `GCS_A2A_PORT` unset or `8732` is refused. Tests that need a hub must
   bind an ephemeral port (existing `_free_port()` helpers).
4. **Refuse live Palemon paths:** launching `hub.py`,
   `start-studio-bus.sh start`, `start-taskboard.sh start`, `mcp-http.sh`,
   or `mcp_http_gateway.py` with `GCS_A2A_STATE` / `GCS_TASKBOARD_DB` /
   `--db` under `/…/palemon/.a2a-state` raises `LiveStudioStateError`.
   `--help` / `stop` / `status` are not launches.

The plugin does **not** exec `start-studio-bus.sh start`, does **not**
recycle leftover dispatch, and does **not** talk to the live hub.

## How to run

Ship-gate (unsets, then pytest, then secret scan):

```bash
unset GCS_ACP_SEATS GCS_MIND_SEATS GCS_A2A_STATE GCS_A2A_REGISTRY GCS_TASKBOARD_DB
.venv/bin/pytest -q
python3 scripts/secret_scan.py
```

`scripts/ci/ship-gate.sh` performs that unset. Do not use `--override-ini`.
Do not point pytest at the live Palemon bus.

## Out of scope

This slice does not remint leftover occupancy / launch-floor siblings,
hub COMPLETE siblings, or GCS #45 purge-delete. Extra High pin stays
`grok-4.6` xhigh `fast=false`.
