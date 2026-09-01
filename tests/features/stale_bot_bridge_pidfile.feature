# Hive stale membership: a leftover bot-bridge.pid is not a live daemon.
# Executable binding: tests/test_stale_bot_bridge_pidfile.py
# Distinct from GCS #74 (GCS_BOT_BRIDGE default-off spawn when the pidfile is missing).
# PAL-25 / LIV-85 adjacent. Do not revive Emerald, Agent Kanban, or palemon leftover #165/#167.

Feature: stale bot-bridge.pid is not liveness
  Existence of bot-bridge.pid does not mean bot-bridge is running.
  recover.sh and doctor.sh must remove a pidfile whose process is dead
  and must not start bot-bridge.

  Scenario: doctor removes a dead pidfile and does not start bot-bridge
    Given a bot-bridge.pid that points at a process that is not running
    When ./doctor.sh runs
    Then bot-bridge.pid is gone
    And no bot-bridge.py process was started for that GCS_A2A_STATE

  Scenario: recover removes a dead pidfile and does not start bot-bridge
    Given leftover hub/dispatch/shepherd pids so recover starts the bus
    And a bot-bridge.pid that points at a process that is not running
    When ./recover.sh runs (not a dry-run)
    Then stdout includes RECOVER_OK
    And stdout does not include STUDIO_BUS_BOT_BRIDGE_START
    And bot-bridge.pid is gone
    And no bot-bridge.py process was started for that GCS_A2A_STATE

  Scenario: a live leftover bot-bridge.pid is kept
    Given a bot-bridge.pid whose process is still running
    When ./doctor.sh runs
    Then bot-bridge.pid still names that live pid
    And the process was not killed
