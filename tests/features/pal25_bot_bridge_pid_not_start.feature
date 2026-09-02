# PAL-25 remaining (beat1849). Executable binding:
# tests/test_pal25_bot_bridge_pid_not_start.py
# BDD in Action: demonstrate, don't theatre. Looks Good to Me: no LGTM without evidence.
#
# Distinct from:
#   GCS #74 / #108 — missing pidfile spawn skip (want_bot_bridge)
#   GCS #36 — default keep-alive of leftover live pid (do not rebase)
#   GCS #77 — stale/dead pidfile tombstone bot-bridge.standby (do not rebase)
#   GCS #131 — beat1740 leftover-pid eviction (do not rebase)
#
# This ticket: leftover bot-bridge.pid is not a default start.
# recover.sh / start-studio-bus.sh start must not restart a live bot-bridge pid
# when GCS_BOT_BRIDGE=1 (ALREADY, same pid). Default/unset/0 must not keep
# leftover live pid as STUDIO_BUS_BOT_BRIDGE_ALREADY (kill-after-RECOVER).

Feature: leftover bot-bridge.pid is not a default start
  A live leftover bot-bridge.pid must not count as a default start.
  Default recover/start evicts leftover Bot wake. Opt-in keeps the same pid.

  Scenario: recover with leftover live pid and GCS_BOT_BRIDGE unset
    Given a leftover studio bus with a live bot-bridge.pid stand-in
    And GCS_BOT_BRIDGE is unset
    When ./recover.sh runs (not a dry-run)
    Then stdout includes RECOVER_OK
    And stdout does not include STUDIO_BUS_BOT_BRIDGE_START
    And stdout does not include STUDIO_BUS_BOT_BRIDGE_ALREADY
    And stdout includes STUDIO_BUS_BOT_BRIDGE_SKIP or RECOVER_BOT_BRIDGE_EVICT
    And the leftover bot-bridge pid is dead

  Scenario: recover with leftover live pid while hub HTTP is already up
    Given leftover live bot-bridge.pid
    And hub /health already returns 200 so recover does not start the bus
    And GCS_BOT_BRIDGE is unset
    When ./recover.sh runs
    Then the leftover bot-bridge pid is dead
    And kill-after-RECOVER is not required

  Scenario: start-studio-bus.sh start with leftover live pid and default off
    Given leftover live bot-bridge.pid
    And GCS_BOT_BRIDGE is unset or 0
    When scripts/a2a/start-studio-bus.sh start runs
    Then stdout does not include STUDIO_BUS_BOT_BRIDGE_ALREADY
    And stdout does not include STUDIO_BUS_BOT_BRIDGE_START
    And the leftover pid is dead

  Scenario: opt-in start must not restart a live bot-bridge pid
    Given leftover live bot-bridge.pid
    And GCS_BOT_BRIDGE=1
    When scripts/a2a/start-studio-bus.sh start runs
    Then stdout includes STUDIO_BUS_BOT_BRIDGE_ALREADY
    And stdout does not include STUDIO_BUS_BOT_BRIDGE_START
    And stdout does not include STUDIO_BUS_BOT_BRIDGE_STOP
    And the leftover pid is still that same live process
