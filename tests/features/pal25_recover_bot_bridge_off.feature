# PAL-25. Executable binding: tests/test_health_recover.py
# BDD in Action: demonstrate, don't theatre. Looks Good to Me: no LGTM without evidence.
# Distinct from GCS #36 (live leftover bot-bridge.pid keep-alive).
# This ticket is default-off spawn when the pidfile is missing.
# Leftover live pid remaining: tests/features/pal25_bot_bridge_pid_not_start.feature

Feature: wipe/recover must not resurrect bot-bridge
  Bot seats stay standby. GCS_BOT_BRIDGE defaults off.
  recover.sh calls start-studio-bus.sh start with no --daemons and must
  not spawn scripts/a2a/bot-bridge.py when the knob is unset or 0.

  Scenario: recover with GCS_BOT_BRIDGE unset does not start bot-bridge
    Given a leftover studio bus with hub/dispatch/shepherd pids and no bot-bridge pid
    And GCS_BOT_BRIDGE is unset
    When ./recover.sh runs (not a dry-run)
    Then stdout includes RECOVER_OK
    And stdout does not include STUDIO_BUS_BOT_BRIDGE_START
    And stdout includes STUDIO_BUS_BOT_BRIDGE_SKIP
    And no live bot-bridge.py process is bound to that GCS_A2A_STATE

  Scenario: recover with GCS_BOT_BRIDGE=0 does not start bot-bridge
    Given a leftover studio bus with no bot-bridge pid
    And GCS_BOT_BRIDGE=0
    When ./recover.sh runs
    Then bot-bridge is not started

  Scenario: recover with GCS_BOT_BRIDGE=1 still starts bot-bridge
    Given a leftover studio bus with no bot-bridge pid
    And GCS_BOT_BRIDGE=1
    When ./recover.sh runs
    Then stdout includes STUDIO_BUS_BOT_BRIDGE_START
    And a live bot-bridge.py process is bound to that GCS_A2A_STATE
