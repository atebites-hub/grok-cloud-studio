# Ship-gate FAT: start-studio-bus.sh / recover.sh / doctor.sh never start
# or reconnect Agent Kanban (`ak` / AMA / scripts/studio/agent-kanban).
# Board stays tcarac/taskboard. Do not reintroduce the tree.
#
# Distinct from wipe-kit GCS #94 (Tailscale / systemd recover / WIPE.md path)
# and seat taskboard stdio MCP GCS #100. This slice is bus + recover + doctor.
#
# Living Sky (linear.app/livingsky, team LIV). NEVER Black Swan.
# Never Bot CloudAgent. Extra High stays grok-4.6 xhigh, fast=false.

Feature: Studio bus, recover, and doctor never reconnect Agent Kanban
  Agent Kanban was removed. Mission control is tcarac/taskboard.
  Leftover `ak` / `ama` on PATH, PALEMON_AK_BRIDGE=1, and a reappeared
  scripts/studio/agent-kanban tree must not start or reconnect AK.

  Scenario: start-studio-bus.sh start does not exec ak or ama
    Given leftover ak and ama binaries on PATH that log every invocation
    And PALEMON_AK_BRIDGE is unset or 0
    When scripts/a2a/start-studio-bus.sh start runs (no --daemons)
    Then STUDIO_BUS_READY is printed
    And the honey-pot log is empty
    And scripts/studio/agent-kanban is not created

  Scenario: start-studio-bus.sh refuses PALEMON_AK_BRIDGE=1
    Given PALEMON_AK_BRIDGE=1 in the environment or studio.env
    When start-studio-bus.sh start runs
    Then the command exits non-zero with AK_REFUSE
    And hub is not started
    And ak / ama are not exec'd

  Scenario: recover.sh does not exec ak or reconnect AMA
    Given leftover ak and ama on PATH
    And the hub is down
    When ./recover.sh runs (dry-run or live, NO --daemons)
    Then it may start start-studio-bus.sh / start-taskboard.sh / mcp-http.sh
    And it does not exec ak, ama, or scripts/studio/agent-kanban
    And it does not launch Cursor Cloud or a Bot CloudAgent

  Scenario: recover.sh refuses PALEMON_AK_BRIDGE=1
    Given PALEMON_AK_BRIDGE=1
    When ./recover.sh runs
    Then the command exits non-zero with AK_REFUSE
    And RECOVER_OK is not printed
    And ak / ama are not exec'd

  Scenario: doctor.sh does not start Agent Kanban
    Given leftover ak and ama on PATH
    When ./doctor.sh runs with GCS_BOT_BIND_OPTIONAL=1
    Then doctor does not exec ak or ama
    And CURSOR_API_KEY is not printed

  Scenario: doctor.sh fails closed on reconnect temptation
    Given PALEMON_AK_BRIDGE=1 or GCS_ROOT has scripts/studio/agent-kanban
    When ./doctor.sh runs
    Then doctor exits non-zero
    And the reason names Agent Kanban
    And the tree is not created in this repository checkout
