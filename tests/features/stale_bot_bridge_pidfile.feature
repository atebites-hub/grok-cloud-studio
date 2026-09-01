# Hive stale membership: a leftover bot-bridge.pid is not a live daemon.
# Executable binding: tests/test_stale_bot_bridge_pidfile.py
# Distinct from GCS #74 (GCS_BOT_BRIDGE default-off spawn when the pidfile is missing).
# PAL-25 / LIV-85 adjacent. Do not revive Emerald, Agent Kanban, or palemon leftover #165/#167.

Feature: stale bot-bridge.pid is not liveness
  Existence of bot-bridge.pid does not mean bot-bridge is running.
  recover.sh, doctor.sh, health_check.sh, and host start-studio-bus.sh
  must remove a pidfile whose process is dead and must not start bot-bridge.
  Eviction is durable: a later host start must not resurrect bot-bridge.

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

  Scenario: host start after stale eviction does not resurrect bot-bridge
    Given leftover hub/dispatch/shepherd pids
    And a bot-bridge.pid that points at a process that is not running
    When start-studio-bus.sh start runs
    Then bot-bridge.pid is gone
    And bot-bridge.standby exists
    And no bot-bridge.py process was started
    When start-studio-bus.sh start runs again
    Then stdout does not include STUDIO_BUS_BOT_BRIDGE_START
    And no bot-bridge.py process was started

  Scenario: health_check evicts a dead pidfile without starting bot-bridge
    Given a bot-bridge.pid that points at a process that is not running
    When ./health_check.sh runs
    Then bot-bridge.pid is gone
    And bot-bridge.standby exists
    And no bot-bridge.py process was started

  Scenario: host start after doctor eviction does not resurrect bot-bridge
    Given leftover hub/dispatch/shepherd pids
    And a bot-bridge.pid that points at a process that is not running
    When ./doctor.sh runs
    Then bot-bridge.pid is gone
    And bot-bridge.standby exists
    When start-studio-bus.sh start runs
    Then stdout does not include STUDIO_BUS_BOT_BRIDGE_START
    And no bot-bridge.py process was started
